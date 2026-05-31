"""Public WS kline updater for the rolling candle cache.

The updater consumes Binance public kline messages, accepts only closed candles
for the configured base timeframe and rebuilds synthetic timeframe series in
the in-memory cache. It does not log every WS tick; callers log stream lifecycle
and aggregate results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
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
