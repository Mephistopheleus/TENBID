"""System supervisor.

Owns liveness: config load, event log, data warmup, cycle runner, reconnects
and graceful shutdown. The current runtime validates TESTNET mode, builds the
first MarketSnapshot from REST warmup and runs one safe HOLD cycle.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from nova.core.config_loader import ConfigLoader, RuntimeConfig
from nova.core.event_log import EventLog
from nova.core.events import Event, EventTypes
from nova.core.history_db import HistoryDB
from nova.core.ids import RUN, new_id
from nova.core.safety_kernel import SafetyKernel
from nova.data.binance_rest import BinanceRestClient, BinanceRestConfig
from nova.data.binance_ws import BinanceWsClient, BinanceWsConfig
from nova.data.candle_cache import CandleCache
from nova.data.orderbook_cache import RateLimitedOrderbookCache
from nova.data.snapshot_refresh import (
    MarketSnapshotRefreshConfig,
    MarketSnapshotRefreshResult,
    MarketSnapshotRefreshService,
)
from nova.data.warmup import DataWarmupConfig, DataWarmupResult, MarketDataWarmupService
from nova.data.ws_kline_updater import (
    WsKlineCacheUpdater,
    WsKlineLoopConfig,
    WsKlineStreamLoop,
    WsKlineUpdaterConfig,
)
from nova.supervisor.cycle_runner import CycleRunner


class SystemSupervisor:
    def __init__(self, root_dir: str | Path = ".") -> None:
        self.root_dir = Path(root_dir).resolve()

    def run(self) -> None:
        config = ConfigLoader(self.root_dir).load()
        self._validate_safety(config)

        run_id = new_id(RUN)
        event_log = EventLog(str(config.event_log_path))
        history_db = HistoryDB(config.sqlite_path)
        candle_cache = CandleCache()
        orderbook_cache = RateLimitedOrderbookCache(ttl_sec=config.orderbook_ttl_sec)

        self._record(
            event_log,
            history_db,
            Event(
                event_type=EventTypes.SYSTEM_STARTED,
                run_id=run_id,
                source="SystemSupervisor",
                payload={
                    "trading_mode": config.trading_mode,
                    "symbol": config.symbol,
                    "base_timeframe": config.base_timeframe,
                    "profile_id": config.profile.profile_id,
                },
            ),
        )
        self._record(
            event_log,
            history_db,
            Event(
                event_type=EventTypes.CONFIG_LOADED,
                run_id=run_id,
                source="SystemSupervisor",
                payload={
                    "event_log_path": str(config.event_log_path),
                    "sqlite_path": str(config.sqlite_path),
                    "synthetic_timeframes": config.synthetic_timeframes,
                    "warmup_candles": config.warmup_candles,
                    "use_ws_klines": config.use_ws_klines,
                    "ws_kline_mode": config.ws_kline_mode,
                    "ws_startup_probe_messages": config.ws_startup_probe_messages,
                    "ws_startup_probe_timeout_sec": config.ws_startup_probe_timeout_sec,
                    "ws_loop_max_runtime_sec": config.ws_loop_max_runtime_sec,
                    "ws_loop_max_reconnects": config.ws_loop_max_reconnects,
                    "native_tf_reconcile_enabled": config.native_tf_reconcile_enabled,
                    "reconcile_enabled": config.reconcile_enabled,
                    "reconcile_candles": config.reconcile_candles,
                    "orderbook_mode": config.orderbook_mode,
                },
            ),
        )
        self._record(
            event_log,
            history_db,
            Event(
                event_type=EventTypes.PROFILE_APPLIED,
                run_id=run_id,
                source="SystemSupervisor",
                payload=config.profile.to_dict(),
            ),
        )

        warmup_result = None
        warmup_error = None
        current_market_snapshot = None
        try:
            warmup_result = self._warmup_market_data(
                config,
                run_id,
                event_log,
                history_db,
                candle_cache,
                orderbook_cache,
            )
            current_market_snapshot = warmup_result.snapshot
        except Exception as exc:  # noqa: BLE001 - safety path records the failure and continues to HOLD.
            warmup_error = str(exc)
            self._record(
                event_log,
                history_db,
                Event(
                    event_type=EventTypes.DATA_WARMUP_FAILED,
                    run_id=run_id,
                    source="SystemSupervisor",
                    payload={
                        "symbol": config.symbol,
                        "base_timeframe": config.base_timeframe,
                        "warmup_candles": config.warmup_candles,
                        "error": warmup_error,
                    },
                ),
            )

        if warmup_result and config.use_ws_klines and warmup_result.snapshot.quality.is_usable:
            self._run_ws_kline_runtime(config, run_id, event_log, history_db, candle_cache)
        if warmup_result and config.reconcile_enabled and warmup_result.snapshot.quality.is_usable:
            refresh_result = self._refresh_market_snapshot(
                config,
                run_id,
                event_log,
                history_db,
                candle_cache,
                orderbook_cache,
            )
            if refresh_result:
                current_market_snapshot = refresh_result.snapshot

        plan = CycleRunner(
            run_id=run_id,
            config=config,
            event_log=event_log,
            history_db=history_db,
            market_snapshot=current_market_snapshot,
            warmup_error=warmup_error,
        ).run_once()

        print(f"NOVA run {run_id} completed: {plan.decision} ({plan.reason})")

    def _warmup_market_data(
        self,
        config: RuntimeConfig,
        run_id: str,
        event_log: EventLog,
        history_db: HistoryDB,
        candle_cache: CandleCache,
        orderbook_cache: RateLimitedOrderbookCache,
    ) -> DataWarmupResult:
        self._record(
            event_log,
            history_db,
            Event(
                event_type=EventTypes.DATA_WARMUP_STARTED,
                run_id=run_id,
                source="SystemSupervisor",
                payload={
                    "symbol": config.symbol,
                    "base_timeframe": config.base_timeframe,
                    "synthetic_timeframes": config.synthetic_timeframes,
                    "warmup_candles": config.warmup_candles,
                    "native_tf_reconcile_enabled": config.native_tf_reconcile_enabled,
                    "orderbook_mode": config.orderbook_mode,
                },
            ),
        )

        rest_client = BinanceRestClient(
            BinanceRestConfig(
                base_url=config.public_rest_base_url,
                market_type=config.market_type,
                timeout_sec=config.rest_timeout_sec,
            )
        )
        warmup = MarketDataWarmupService(rest_client, cache=candle_cache, orderbook_cache=orderbook_cache)
        result = warmup.warmup(
            DataWarmupConfig(
                symbol=config.symbol,
                base_timeframe=config.base_timeframe,
                synthetic_timeframes=config.synthetic_timeframes,
                warmup_candles=config.warmup_candles,
                fetch_native_timeframes=config.native_tf_reconcile_enabled,
                fetch_orderbook=self._fetch_orderbook_during_warmup(config.orderbook_mode),
                orderbook_limit=config.orderbook_limit,
            )
        )
        history_db.log_market_snapshot(result.snapshot)

        candle_counts = {timeframe: series.count for timeframe, series in sorted(result.snapshot.candles.items())}
        native_issue_codes = {
            timeframe: details.get("issue_codes", [])
            for timeframe, details in sorted(result.native_reconciliation.items())
        }
        self._record(
            event_log,
            history_db,
            Event(
                event_type=EventTypes.MARKET_SNAPSHOT_CREATED,
                run_id=run_id,
                source="SystemSupervisor",
                payload={
                    "snapshot_id": result.snapshot.snapshot_id,
                    "symbol": result.snapshot.primary_symbol,
                    "base_timeframe": result.snapshot.base_timeframe,
                    "quality_score": result.snapshot.quality.score,
                    "quality_usable": result.snapshot.quality.is_usable,
                    "candle_counts": candle_counts,
                },
            ),
        )
        self._record(
            event_log,
            history_db,
            Event(
                event_type=EventTypes.DATA_WARMUP_COMPLETED,
                run_id=run_id,
                source="SystemSupervisor",
                payload={
                    "snapshot_id": result.snapshot.snapshot_id,
                    "symbol": result.snapshot.primary_symbol,
                    "base_timeframe": result.snapshot.base_timeframe,
                    "quality_score": result.snapshot.quality.score,
                    "quality_usable": result.snapshot.quality.is_usable,
                    "candle_counts": candle_counts,
                    "native_issue_codes": native_issue_codes,
                    "ws_klines_configured": config.use_ws_klines,
                    "ws_kline_mode": config.ws_kline_mode,
                },
            ),
        )
        return result

    def _refresh_market_snapshot(
        self,
        config: RuntimeConfig,
        run_id: str,
        event_log: EventLog,
        history_db: HistoryDB,
        candle_cache: CandleCache,
        orderbook_cache: RateLimitedOrderbookCache,
    ) -> MarketSnapshotRefreshResult | None:
        self._record(
            event_log,
            history_db,
            Event(
                event_type=EventTypes.DATA_RECONCILIATION_STARTED,
                run_id=run_id,
                source="SystemSupervisor",
                payload={
                    "symbol": config.symbol,
                    "base_timeframe": config.base_timeframe,
                    "synthetic_timeframes": config.synthetic_timeframes,
                    "reconcile_candles": config.reconcile_candles,
                    "orderbook_mode": config.orderbook_mode,
                },
            ),
        )

        rest_client = BinanceRestClient(
            BinanceRestConfig(
                base_url=config.public_rest_base_url,
                market_type=config.market_type,
                timeout_sec=config.rest_timeout_sec,
            )
        )
        try:
            result = MarketSnapshotRefreshService(rest_client, cache=candle_cache, orderbook_cache=orderbook_cache).refresh(
                MarketSnapshotRefreshConfig(
                    symbol=config.symbol,
                    base_timeframe=config.base_timeframe,
                    synthetic_timeframes=config.synthetic_timeframes,
                    reconcile_candles=config.reconcile_candles,
                    snapshot_candle_limit=config.warmup_candles,
                    fetch_orderbook=self._fetch_orderbook_during_refresh(config.orderbook_mode),
                    orderbook_limit=config.orderbook_limit,
                )
            )
        except Exception as exc:  # noqa: BLE001 - reconciliation is a control layer, not a runtime kill switch.
            self._record(
                event_log,
                history_db,
                Event(
                    event_type=EventTypes.DATA_RECONCILIATION_FAILED,
                    run_id=run_id,
                    source="SystemSupervisor",
                    payload={
                        "symbol": config.symbol,
                        "base_timeframe": config.base_timeframe,
                        "reconcile_candles": config.reconcile_candles,
                        "error": str(exc),
                    },
                ),
            )
            return None

        history_db.log_market_snapshot(result.snapshot)
        candle_counts = {timeframe: series.count for timeframe, series in sorted(result.snapshot.candles.items())}
        self._record(
            event_log,
            history_db,
            Event(
                event_type=EventTypes.MARKET_SNAPSHOT_CREATED,
                run_id=run_id,
                source="SystemSupervisor",
                payload={
                    "snapshot_id": result.snapshot.snapshot_id,
                    "symbol": result.snapshot.primary_symbol,
                    "base_timeframe": result.snapshot.base_timeframe,
                    "quality_score": result.snapshot.quality.score,
                    "quality_usable": result.snapshot.quality.is_usable,
                    "candle_counts": candle_counts,
                    "refresh_type": "rest_reconciliation",
                },
            ),
        )
        self._record(
            event_log,
            history_db,
            Event(
                event_type=EventTypes.DATA_RECONCILIATION_COMPLETED,
                run_id=run_id,
                source="SystemSupervisor",
                payload={
                    "snapshot_id": result.snapshot.snapshot_id,
                    "symbol": result.snapshot.primary_symbol,
                    "base_timeframe": result.snapshot.base_timeframe,
                    "quality_score": result.snapshot.quality.score,
                    "quality_usable": result.snapshot.quality.is_usable,
                    "candle_counts": candle_counts,
                    "reconciled_candle_count": result.reconciled_candle_count,
                    "matched_candle_count": result.matched_candle_count,
                    "filled_candle_count": result.filled_candle_count,
                    "replaced_candle_count": result.replaced_candle_count,
                    "mismatch_open_times": result.mismatch_open_times,
                    "issue_codes": result.snapshot.quality.issue_codes,
                },
            ),
        )
        return result

    def _run_ws_kline_runtime(
        self,
        config: RuntimeConfig,
        run_id: str,
        event_log: EventLog,
        history_db: HistoryDB,
        candle_cache: CandleCache,
    ) -> None:
        mode = config.ws_kline_mode.lower()
        if mode == "startup_probe":
            self._run_ws_kline_startup_probe(config, run_id, event_log, history_db, candle_cache)
            return
        if mode in {"loop_slice", "live_loop"}:
            self._run_ws_kline_loop(config, run_id, event_log, history_db, candle_cache, mode=mode)
            return

        self._record(
            event_log,
            history_db,
            Event(
                event_type=EventTypes.WS_KLINE_STREAM_FAILED,
                run_id=run_id,
                source="SystemSupervisor",
                payload={
                    "symbol": config.symbol,
                    "base_timeframe": config.base_timeframe,
                    "mode": mode,
                    "error": "unsupported_ws_kline_mode",
                },
            ),
        )

    def _run_ws_kline_startup_probe(
        self,
        config: RuntimeConfig,
        run_id: str,
        event_log: EventLog,
        history_db: HistoryDB,
        candle_cache: CandleCache,
    ) -> None:
        ws_client = BinanceWsClient(BinanceWsConfig(base_url=config.public_ws_base_url))
        updater_config = WsKlineUpdaterConfig(
            symbol=config.symbol,
            base_timeframe=config.base_timeframe,
            synthetic_timeframes=config.synthetic_timeframes,
            max_messages=config.ws_startup_probe_messages,
            timeout_sec=config.ws_startup_probe_timeout_sec,
            closed_candle_target=1,
        )
        stream_url = ws_client.kline_stream_url(config.symbol, config.base_timeframe)
        self._record(
            event_log,
            history_db,
            Event(
                event_type=EventTypes.WS_KLINE_STREAM_STARTED,
                run_id=run_id,
                source="SystemSupervisor",
                payload={
                    "symbol": config.symbol,
                    "base_timeframe": config.base_timeframe,
                    "stream_url": stream_url,
                    "max_messages": updater_config.max_messages,
                    "timeout_sec": updater_config.timeout_sec,
                    "mode": "startup_probe",
                },
            ),
        )

        try:
            result = WsKlineCacheUpdater(ws_client, candle_cache).consume(updater_config)
        except Exception as exc:  # noqa: BLE001 - WS failure must not break the safe HOLD cycle.
            self._record(
                event_log,
                history_db,
                Event(
                    event_type=EventTypes.WS_KLINE_STREAM_FAILED,
                    run_id=run_id,
                    source="SystemSupervisor",
                    payload={
                        "symbol": config.symbol,
                        "base_timeframe": config.base_timeframe,
                        "stream_url": stream_url,
                        "mode": "startup_probe",
                        "error": str(exc),
                    },
                ),
            )
            return

        event_type = EventTypes.WS_KLINE_STREAM_COMPLETED if result.is_usable else EventTypes.WS_KLINE_STREAM_FAILED
        self._record(
            event_log,
            history_db,
            Event(
                event_type=event_type,
                run_id=run_id,
                source="SystemSupervisor",
                payload={
                    **asdict(result),
                    "symbol": config.symbol,
                    "base_timeframe": config.base_timeframe,
                    "mode": "startup_probe",
                    "closed_candles_required": False,
                },
            ),
        )

    def _run_ws_kline_loop(
        self,
        config: RuntimeConfig,
        run_id: str,
        event_log: EventLog,
        history_db: HistoryDB,
        candle_cache: CandleCache,
        mode: str,
    ) -> None:
        ws_client = BinanceWsClient(BinanceWsConfig(base_url=config.public_ws_base_url))
        loop_config = WsKlineLoopConfig(
            symbol=config.symbol,
            base_timeframe=config.base_timeframe,
            synthetic_timeframes=config.synthetic_timeframes,
            max_runtime_sec=config.ws_loop_max_runtime_sec,
            connection_timeout_sec=config.ws_loop_connection_timeout_sec,
            max_reconnects=config.ws_loop_max_reconnects,
            reconnect_backoff_sec=config.ws_loop_reconnect_backoff_sec,
        )
        stream_url = ws_client.kline_stream_url(config.symbol, config.base_timeframe)
        self._record(
            event_log,
            history_db,
            Event(
                event_type=EventTypes.WS_KLINE_LOOP_STARTED,
                run_id=run_id,
                source="SystemSupervisor",
                payload={
                    "symbol": config.symbol,
                    "base_timeframe": config.base_timeframe,
                    "stream_url": stream_url,
                    "mode": mode,
                    "max_runtime_sec": loop_config.max_runtime_sec,
                    "connection_timeout_sec": loop_config.connection_timeout_sec,
                    "max_reconnects": loop_config.max_reconnects,
                    "reconnect_backoff_sec": loop_config.reconnect_backoff_sec,
                    "bounded_runtime": True,
                },
            ),
        )

        try:
            result = WsKlineStreamLoop(ws_client, candle_cache).run(loop_config)
        except Exception as exc:  # noqa: BLE001 - WS loop failure must not break the safe HOLD cycle.
            self._record(
                event_log,
                history_db,
                Event(
                    event_type=EventTypes.WS_KLINE_LOOP_STOPPED,
                    run_id=run_id,
                    source="SystemSupervisor",
                    payload={
                        "symbol": config.symbol,
                        "base_timeframe": config.base_timeframe,
                        "stream_url": stream_url,
                        "mode": mode,
                        "stopped_reason": "exception",
                        "issue_codes": ["ws_kline_loop_failed"],
                        "error": str(exc),
                    },
                ),
            )
            return

        self._record(
            event_log,
            history_db,
            Event(
                event_type=EventTypes.WS_KLINE_LOOP_STOPPED,
                run_id=run_id,
                source="SystemSupervisor",
                payload={
                    **asdict(result),
                    "symbol": config.symbol,
                    "base_timeframe": config.base_timeframe,
                    "mode": mode,
                    "bounded_runtime": True,
                },
            ),
        )

    @staticmethod
    def _validate_safety(config: RuntimeConfig) -> None:
        kernel = SafetyKernel()
        kernel.assert_mode_allowed(config.trading_mode, live_unlock=config.live_unlock)
        kernel.assert_symbol_allowed(config.symbol)

    @staticmethod
    def _fetch_orderbook_during_warmup(orderbook_mode: str) -> bool:
        return orderbook_mode.lower() in {"warmup", "startup", "always"}

    @staticmethod
    def _fetch_orderbook_during_refresh(orderbook_mode: str) -> bool:
        return orderbook_mode.lower() in {"refresh", "reconciliation", "always"}

    @staticmethod
    def _record(event_log: EventLog, history_db: HistoryDB, event: Event) -> None:
        event_log.append(event)
        history_db.log_event(event)
