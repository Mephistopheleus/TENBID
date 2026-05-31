"""Public WS kline updater for the rolling candle cache.

The updater consumes Binance public kline messages, accepts only closed candles
for the configured base timeframe and rebuilds synthetic timeframe series in
the in-memory cache. It does not log every WS tick; callers log stream lifecycle
and aggregate results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic, sleep
from typing import Any, Callable, Dict, List, Optional

from nova.data.binance_ws import BinanceWsClient
from nova.data.candle_cache import CandleCache
from nova.data.models import Candle
from nova.data.synthetic_tf import SyntheticTimeframeBuilder

try:  # Optional runtime dependency in this clean-room stage.
    from websocket import create_connection
except ImportError:  # pragma: no cover - covered by runtime issue metadata.
    create_connection = None  # type: ignore[assignment]


ConnectionFactory = Callable[..., Any]


@dataclass(frozen=True)
class WsKlineUpdaterConfig:
    symbol: str
    base_timeframe: str
    synthetic_timeframes: List[str]
    max_messages: int = 5
    timeout_sec: float = 10.0
    closed_candle_target: int = 1


@dataclass(frozen=True)
class WsKlineUpdateResult:
    stream_url: str
    message_count: int = 0
    closed_candle_count: int = 0
    open_candle_count: int = 0
    ignored_message_count: int = 0
    latest_closed_open_time: Optional[str] = None
    latest_closed_close_time: Optional[str] = None
    cache_counts: Dict[str, int] = field(default_factory=dict)
    issue_codes: List[str] = field(default_factory=list)
    error_message: Optional[str] = None

    @property
    def is_usable(self) -> bool:
        return not self.issue_codes


@dataclass(frozen=True)
class WsKlineLoopConfig:
    symbol: str
    base_timeframe: str
    synthetic_timeframes: List[str]
    max_runtime_sec: float = 15.0
    connection_timeout_sec: float = 5.0
    max_reconnects: int = 2
    reconnect_backoff_sec: float = 1.0
    max_messages_per_connection: int = 0


@dataclass(frozen=True)
class WsKlineLoopResult:
    stream_url: str
    connection_attempts: int = 0
    reconnect_count: int = 0
    message_count: int = 0
    closed_candle_count: int = 0
    open_candle_count: int = 0
    ignored_message_count: int = 0
    latest_closed_open_time: Optional[str] = None
    latest_closed_close_time: Optional[str] = None
    cache_counts: Dict[str, int] = field(default_factory=dict)
    stopped_reason: str = "not_started"
    issue_codes: List[str] = field(default_factory=list)
    error_message: Optional[str] = None

    @property
    def is_usable(self) -> bool:
        return not self.issue_codes or self.stopped_reason == "runtime_limit"


class WsKlineCacheUpdater:
    def __init__(
        self,
        ws_client: BinanceWsClient,
        cache: CandleCache,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        self.ws_client = ws_client
        self.cache = cache
        self.connection_factory = connection_factory or create_connection

    def consume(self, config: WsKlineUpdaterConfig) -> WsKlineUpdateResult:
        stream_url = self.ws_client.kline_stream_url(config.symbol, config.base_timeframe)
        if self.connection_factory is None:
            return WsKlineUpdateResult(
                stream_url=stream_url,
                cache_counts=self._cache_counts(config),
                issue_codes=["websocket_client_missing"],
            )

        message_count = 0
        closed_candle_count = 0
        open_candle_count = 0
        ignored_message_count = 0
        latest_closed: Candle | None = None
        issue_codes: List[str] = []
        latest_error: str | None = None
        connection = None
        deadline = monotonic() + max(0.1, config.timeout_sec)

        try:
            connection = self.connection_factory(stream_url, timeout=config.timeout_sec)
            while message_count < config.max_messages and monotonic() < deadline:
                if closed_candle_count >= config.closed_candle_target:
                    break
                raw_message = connection.recv()
                message_count += 1
                candle = self.ws_client.parse_kline_message(raw_message)
                if candle.symbol != config.symbol.upper() or candle.timeframe != config.base_timeframe:
                    ignored_message_count += 1
                    continue
                if not candle.is_closed:
                    open_candle_count += 1
                    continue

                self.cache.update_from_kline(candle)
                self._rebuild_synthetic(config)
                latest_closed = candle
                closed_candle_count += 1
        except TimeoutError:
            issue_codes.append("ws_kline_timeout")
            latest_error = "timeout"
        except Exception as exc:  # noqa: BLE001 - stream failures are reported as data-layer metadata.
            issue_codes.append("ws_kline_stream_failed")
            ignored_message_count += 1
            latest_error = str(exc)
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:  # noqa: BLE001 - close failure must not hide the stream result.
                    issue_codes.append("ws_kline_close_failed")

        return WsKlineUpdateResult(
            stream_url=stream_url,
            message_count=message_count,
            closed_candle_count=closed_candle_count,
            open_candle_count=open_candle_count,
            ignored_message_count=ignored_message_count,
            latest_closed_open_time=latest_closed.open_time if latest_closed else None,
            latest_closed_close_time=latest_closed.close_time if latest_closed else None,
            cache_counts=self._cache_counts(config),
            issue_codes=issue_codes,
            error_message=latest_error,
        )

    def apply_message(self, message: str | Dict[str, Any], config: WsKlineUpdaterConfig) -> WsKlineUpdateResult:
        stream_url = self.ws_client.kline_stream_url(config.symbol, config.base_timeframe)
        candle = self.ws_client.parse_kline_message(message)
        if candle.symbol != config.symbol.upper() or candle.timeframe != config.base_timeframe:
            return WsKlineUpdateResult(
                stream_url=stream_url,
                message_count=1,
                ignored_message_count=1,
                cache_counts=self._cache_counts(config),
            )
        if not candle.is_closed:
            return WsKlineUpdateResult(
                stream_url=stream_url,
                message_count=1,
                open_candle_count=1,
                cache_counts=self._cache_counts(config),
            )

        self.cache.update_from_kline(candle)
        self._rebuild_synthetic(config)
        return WsKlineUpdateResult(
            stream_url=stream_url,
            message_count=1,
            closed_candle_count=1,
            latest_closed_open_time=candle.open_time,
            latest_closed_close_time=candle.close_time,
            cache_counts=self._cache_counts(config),
        )

    def _rebuild_synthetic(self, config: WsKlineUpdaterConfig) -> None:
        base_series = self.cache.get_closed(
            timeframe=config.base_timeframe,
            limit=self.cache.max_candles_per_series,
            symbol=config.symbol,
        )
        synthetic = SyntheticTimeframeBuilder(config.synthetic_timeframes).build_all(base_series)
        for series in synthetic.values():
            self.cache.load_series(series)

    def _cache_counts(self, config: WsKlineUpdaterConfig) -> Dict[str, int]:
        timeframes = [config.base_timeframe, *config.synthetic_timeframes]
        return {
            timeframe: self.cache.get_series(config.symbol, timeframe).count
            for timeframe in timeframes
        }


class WsKlineStreamLoop:
    def __init__(
        self,
        ws_client: BinanceWsClient,
        cache: CandleCache,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        self.ws_client = ws_client
        self.cache = cache
        self.connection_factory = connection_factory or create_connection

    def run(self, config: WsKlineLoopConfig) -> WsKlineLoopResult:
        stream_url = self.ws_client.kline_stream_url(config.symbol, config.base_timeframe)
        if self.connection_factory is None:
            return WsKlineLoopResult(
                stream_url=stream_url,
                cache_counts=self._cache_counts(config),
                stopped_reason="dependency_missing",
                issue_codes=["websocket_client_missing"],
            )

        deadline = monotonic() + max(0.1, config.max_runtime_sec)
        connection_attempts = 0
        reconnect_count = 0
        message_count = 0
        closed_candle_count = 0
        open_candle_count = 0
        ignored_message_count = 0
        latest_closed: Candle | None = None
        issue_codes: List[str] = []
        latest_error: str | None = None
        stopped_reason = "runtime_limit"

        while monotonic() < deadline:
            connection = None
            connection_message_count = 0
            connection_attempts += 1
            try:
                connection = self.connection_factory(stream_url, timeout=config.connection_timeout_sec)
                while monotonic() < deadline:
                    if config.max_messages_per_connection and connection_message_count >= config.max_messages_per_connection:
                        stopped_reason = "message_limit"
                        break
                    raw_message = connection.recv()
                    message_count += 1
                    connection_message_count += 1
                    candle = self.ws_client.parse_kline_message(raw_message)
                    if candle.symbol != config.symbol.upper() or candle.timeframe != config.base_timeframe:
                        ignored_message_count += 1
                        continue
                    if not candle.is_closed:
                        open_candle_count += 1
                        continue

                    self.cache.update_from_kline(candle)
                    self._rebuild_synthetic(config)
                    latest_closed = candle
                    closed_candle_count += 1
                if stopped_reason == "message_limit":
                    break
            except Exception as exc:  # noqa: BLE001 - reconnect policy owns WS stream failures.
                latest_error = str(exc)
                if monotonic() >= deadline:
                    stopped_reason = "runtime_limit"
                    break
                if reconnect_count >= config.max_reconnects:
                    stopped_reason = "reconnect_limit"
                    issue_codes.append("ws_kline_reconnect_limit_reached")
                    break
                reconnect_count += 1
                self._sleep_before_reconnect(config, reconnect_count, deadline)
            finally:
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:  # noqa: BLE001 - close failure is metadata, not a runtime crash.
                        issue_codes.append("ws_kline_close_failed")

        return WsKlineLoopResult(
            stream_url=stream_url,
            connection_attempts=connection_attempts,
            reconnect_count=reconnect_count,
            message_count=message_count,
            closed_candle_count=closed_candle_count,
            open_candle_count=open_candle_count,
            ignored_message_count=ignored_message_count,
            latest_closed_open_time=latest_closed.open_time if latest_closed else None,
            latest_closed_close_time=latest_closed.close_time if latest_closed else None,
            cache_counts=self._cache_counts(config),
            stopped_reason=stopped_reason,
            issue_codes=issue_codes,
            error_message=latest_error,
        )

    def _rebuild_synthetic(self, config: WsKlineLoopConfig) -> None:
        base_series = self.cache.get_closed(
            timeframe=config.base_timeframe,
            limit=self.cache.max_candles_per_series,
            symbol=config.symbol,
        )
        synthetic = SyntheticTimeframeBuilder(config.synthetic_timeframes).build_all(base_series)
        for series in synthetic.values():
            self.cache.load_series(series)

    def _cache_counts(self, config: WsKlineLoopConfig) -> Dict[str, int]:
        timeframes = [config.base_timeframe, *config.synthetic_timeframes]
        return {
            timeframe: self.cache.get_series(config.symbol, timeframe).count
            for timeframe in timeframes
        }

    @staticmethod
    def _sleep_before_reconnect(config: WsKlineLoopConfig, reconnect_count: int, deadline: float) -> None:
        delay = max(0.0, config.reconnect_backoff_sec * reconnect_count)
        remaining = deadline - monotonic()
        if delay and remaining > 0:
            sleep(min(delay, remaining))
