"""Market data warmup service.

Builds the first MarketSnapshot from REST data, fills the rolling cache, creates
synthetic timeframes and optionally downloads native higher-timeframe candles for
same-period reconciliation metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from math import ceil
from typing import Any, Dict, List, Optional

from nova.data.binance_rest import BinanceRestClient
from nova.data.candle_cache import CandleCache
from nova.data.models import CandleSeries, DataQualityReport, MarketSnapshot, OrderbookSnapshot
from nova.data.orderbook_cache import RateLimitedOrderbookCache
from nova.data.reconciliation import TimeframeReconciler
from nova.data.synthetic_tf import SyntheticTimeframeBuilder, timeframe_to_minutes


BINANCE_NATIVE_KLINE_INTERVALS = {
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
    "1M",
}


@dataclass(frozen=True)
class DataWarmupConfig:
    symbol: str
    base_timeframe: str
    synthetic_timeframes: List[str]
    warmup_candles: int = 300
    fetch_native_timeframes: bool = True
    fetch_orderbook: bool = False
    orderbook_limit: int = 20


@dataclass(frozen=True)
class DataWarmupResult:
    snapshot: MarketSnapshot
    base_series: CandleSeries
    synthetic_series: Dict[str, CandleSeries]
    native_reconciliation: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class MarketDataWarmupService:
    def __init__(
        self,
        rest_client: BinanceRestClient,
        cache: CandleCache | None = None,
        orderbook_cache: RateLimitedOrderbookCache | None = None,
        reconciler: TimeframeReconciler | None = None,
    ) -> None:
        self.rest_client = rest_client
        self.cache = cache or CandleCache()
        self.orderbook_cache = orderbook_cache
        self.reconciler = reconciler or TimeframeReconciler()

    def warmup(self, config: DataWarmupConfig) -> DataWarmupResult:
        base_series = self.rest_client.get_klines(
            config.symbol,
            config.base_timeframe,
            limit=config.warmup_candles,
        )
        base_quality = self.reconciler.evaluate_candle_series_quality(
            base_series,
            expected_min_count=config.warmup_candles,
        )
        base_series = replace(base_series, quality=base_quality)
        self.cache.load_series(base_series)

        synthetic_builder = SyntheticTimeframeBuilder(config.synthetic_timeframes)
        synthetic_series = synthetic_builder.build_all(base_series)
        synthetic_series = {
            timeframe: replace(series, quality=self._synthetic_quality(series))
            for timeframe, series in synthetic_series.items()
        }
        for series in synthetic_series.values():
            self.cache.load_series(series)

        native_reconciliation: Dict[str, Dict[str, Any]] = {}
        if config.fetch_native_timeframes:
            native_reconciliation = self._fetch_native_reconciliation(base_series, config.synthetic_timeframes)

        orderbook: Optional[OrderbookSnapshot] = None
        orderbook_metadata: Dict[str, Any] = {"requested": config.fetch_orderbook}
        if config.fetch_orderbook:
            if self.orderbook_cache is None:
                orderbook = self.rest_client.get_orderbook(config.symbol, limit=config.orderbook_limit)
                orderbook_metadata = {"requested": True, "fetched": True, "cache_used": False}
            else:
                orderbook_result = self.orderbook_cache.get_orderbook(
                    self.rest_client,
                    config.symbol,
                    config.orderbook_limit,
                    reason="warmup",
                )
                orderbook = orderbook_result.snapshot
                orderbook_metadata = {
                    "requested": True,
                    "fetched": orderbook_result.fetched,
                    "cache_age_sec": orderbook_result.cache_age_sec,
                    "forced": orderbook_result.forced,
                    "reason": orderbook_result.reason,
                }

        candles = {config.base_timeframe: base_series, **synthetic_series}
        snapshot_quality = self._snapshot_quality(base_quality, synthetic_series)
        snapshot = MarketSnapshot(
            primary_symbol=config.symbol.upper(),
            base_timeframe=config.base_timeframe,
            candles=candles,
            orderbook=orderbook,
            quality=snapshot_quality,
            payload={
                "warmup_candles": config.warmup_candles,
                "synthetic_timeframes": config.synthetic_timeframes,
                "native_reconciliation": native_reconciliation,
                "cache_series": sorted(candles.keys()),
                "orderbook": orderbook_metadata,
            },
        )
        return DataWarmupResult(
            snapshot=snapshot,
            base_series=base_series,
            synthetic_series=synthetic_series,
            native_reconciliation=native_reconciliation,
        )

    def _fetch_native_reconciliation(
        self,
        base_series: CandleSeries,
        target_timeframes: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        if not base_series.candles:
            return {}
        start_time_ms = _iso_to_millis(base_series.candles[0].open_time)
        end_time_ms = _iso_to_millis(base_series.candles[-1].close_time)
        base_minutes = timeframe_to_minutes(base_series.timeframe)
        base_window_minutes = max(1, base_series.count * base_minutes)
        report: Dict[str, Dict[str, Any]] = {}
        for timeframe in target_timeframes:
            if timeframe not in BINANCE_NATIVE_KLINE_INTERVALS:
                report[timeframe] = {
                    "native_count": 0,
                    "quality_score": 0.0,
                    "quality_usable": False,
                    "issue_codes": ["native_interval_not_supported"],
                }
                continue
            try:
                target_minutes = timeframe_to_minutes(timeframe)
                limit = max(1, ceil(base_window_minutes / target_minutes) + 1)
                native = self.rest_client.get_klines(
                    base_series.symbol,
                    timeframe,
                    limit=limit,
                    start_time_ms=start_time_ms,
                    end_time_ms=end_time_ms,
                )
                quality = self.reconciler.evaluate_candle_series_quality(native, expected_min_count=1)
                report[timeframe] = {
                    "native_series_id": native.series_id,
                    "native_count": native.count,
                    "requested_limit": limit,
                    "quality_score": quality.score,
                    "quality_usable": quality.is_usable,
                    "issue_codes": quality.issue_codes,
                }
            except Exception as exc:  # noqa: BLE001 - recorded as data quality metadata, not fatal warmup failure.
                report[timeframe] = {
                    "native_count": 0,
                    "quality_score": 0.0,
                    "quality_usable": False,
                    "issue_codes": ["native_reconciliation_failed"],
                    "error": str(exc),
                }
        return report

    @staticmethod
    def _synthetic_quality(series: CandleSeries) -> DataQualityReport:
        continuity = TimeframeReconciler().evaluate_candle_series_quality(series, expected_min_count=1)
        issue_codes = [*series.quality.issue_codes, *continuity.issue_codes]
        return DataQualityReport(
            is_usable=series.quality.is_usable and continuity.is_usable,
            score=min(series.quality.score, continuity.score),
            completeness=continuity.completeness,
            gap_count=continuity.gap_count,
            issue_codes=issue_codes,
            payload={**series.quality.payload, **continuity.payload},
        )

    @staticmethod
    def _snapshot_quality(
        base_quality: DataQualityReport,
        synthetic_series: Dict[str, CandleSeries],
    ) -> DataQualityReport:
        synthetic_scores = [series.quality.score for series in synthetic_series.values()]
        all_scores = [base_quality.score, *synthetic_scores]
        score = min(all_scores) if all_scores else 0.0
        issue_codes = list(base_quality.issue_codes)
        for timeframe, series in synthetic_series.items():
            issue_codes.extend(f"{timeframe}:{code}" for code in series.quality.issue_codes)
        return DataQualityReport(
            is_usable=base_quality.is_usable and score > 0.0,
            score=score,
            completeness=base_quality.completeness,
            gap_count=base_quality.gap_count,
            issue_codes=issue_codes,
            payload={"base_quality_score": base_quality.score, "synthetic_scores": synthetic_scores},
        )


def _iso_to_millis(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
