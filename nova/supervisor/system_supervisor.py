"""System supervisor.

Owns liveness: config load, event log, data warmup, cycle runner, reconnects
and graceful shutdown. The current runtime validates TESTNET mode, builds the
first MarketSnapshot from REST warmup and runs one safe HOLD cycle.
"""

from __future__ import annotations

from pathlib import Path

from nova.core.config_loader import ConfigLoader, RuntimeConfig
from nova.core.event_log import EventLog
from nova.core.events import Event, EventTypes
from nova.core.history_db import HistoryDB
from nova.core.ids import RUN, new_id
from nova.core.safety_kernel import SafetyKernel
from nova.data.binance_rest import BinanceRestClient, BinanceRestConfig
from nova.data.warmup import DataWarmupConfig, DataWarmupResult, MarketDataWarmupService
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
                    "native_tf_reconcile_enabled": config.native_tf_reconcile_enabled,
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
        try:
            warmup_result = self._warmup_market_data(config, run_id, event_log, history_db)
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

        plan = CycleRunner(
            run_id=run_id,
            config=config,
            event_log=event_log,
            history_db=history_db,
            market_snapshot=warmup_result.snapshot if warmup_result else None,
            warmup_error=warmup_error,
        ).run_once()

        print(f"NOVA run {run_id} completed: {plan.decision} ({plan.reason})")

    def _warmup_market_data(
        self,
        config: RuntimeConfig,
        run_id: str,
        event_log: EventLog,
        history_db: HistoryDB,
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
        warmup = MarketDataWarmupService(rest_client)
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
                    "ws_loop_started": False,
                },
            ),
        )
        return result

    @staticmethod
    def _validate_safety(config: RuntimeConfig) -> None:
        kernel = SafetyKernel()
        kernel.assert_mode_allowed(config.trading_mode, live_unlock=config.live_unlock)
        kernel.assert_symbol_allowed(config.symbol)

    @staticmethod
    def _fetch_orderbook_during_warmup(orderbook_mode: str) -> bool:
        return orderbook_mode.lower() in {"warmup", "startup", "always"}

    @staticmethod
    def _record(event_log: EventLog, history_db: HistoryDB, event: Event) -> None:
        event_log.append(event)
        history_db.log_event(event)
