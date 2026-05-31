"""REST reconciliation and MarketSnapshot refresh.

This service is the control layer after REST warmup and WS kline updates: it
uses recent REST candles as the authoritative public reference, reconciles the
rolling CandleCache, rebuilds synthetic timeframes and emits a fresh
MarketSnapshot for the next runtime cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List

from nova.data.binance_rest import BinanceRestClient
from nova.data.candle_cache import CandleCache
from nova.data.models import Candle, CandleSeries, DataQualityReport, MarketSnapshot, OrderbookSnapshot
from nova.data.reconciliation import TimeframeReconciler
from nova.data.synthetic_tf import SyntheticTimeframeBuilder
from nova.data.warmup import MarketDataWarmupService


@dataclass(frozen=True)
class MarketSnapshotRefreshConfig:
    symbol: str
    base_timeframe: str
    synthetic_timeframes: List[str]
    reconcile_candles: int = 120
    snapshot_candle_limit: int = 300
    fetch_orderbook: bool = False
    orderbook_limit: int = 20


@dataclass(frozen=True)
class MarketSnapshotRefreshResult:
    snapshot: MarketSnapshot
    rest_series: CandleSeries
    cache_base_series: CandleSeries
    synthetic_series: Dict[str, CandleSeries]
    reconciled_candle_count: int
    matched_candle_count: int
    filled_candle_count: int
    replaced_candle_count: int
    mismatch_open_times: List[str] = field(default_factory=list)


class MarketSnapshotRefreshService:
    def __init__(
        self,
        rest_client: BinanceRestClient,
        cache: CandleCache,
        reconciler: TimeframeReconciler | None = None,
    ) -> None:
        self.rest_client = rest_client
        self.cache = cache
        self.reconciler = reconciler or TimeframeReconciler()

    def refresh(self, config: MarketSnapshotRefreshConfig) -> MarketSnapshotRefreshResult:
        reconcile_limit = max(1, min(1500, config.reconcile_candles))
        snapshot_limit = max(reconcile_limit, config.snapshot_candle_limit)

        cache_before = self.cache.get_series(config.symbol, config.base_timeframe)
        before_by_open_time = {candle.open_time: candle for candle in cache_before.candles}

        rest_series = self.rest_client.get_klines(
            config.symbol,
            config.base_timeframe,
            limit=reconcile_limit,
        )
        rest_quality = self.reconciler.evaluate_candle_series_quality(
            rest_series,
            expected_min_count=reconcile_limit,
        )
        rest_series = replace(rest_series, quality=rest_quality)

        stats = self._apply_rest_reconciliation(rest_series, before_by_open_time)

        cache_base_series = self.cache.get_closed(
            timeframe=config.base_timeframe,
            limit=snapshot_limit,
            symbol=config.symbol,
        )
        expected_cache_count = max(1, min(snapshot_limit, max(reconcile_limit, rest_series.count)))
        cache_quality = self.reconciler.evaluate_candle_series_quality(
            cache_base_series,
            expected_min_count=expected_cache_count,
        )
        cache_base_series = replace(cache_base_series, quality=cache_quality)

        synthetic_builder = SyntheticTimeframeBuilder(config.synthetic_timeframes)
        synthetic_series = synthetic_builder.build_all(cache_base_series)
        synthetic_series = {
            timeframe: replace(series, quality=MarketDataWarmupService._synthetic_quality(series))
            for timeframe, series in synthetic_series.items()
        }
        for series in synthetic_series.values():
            self.cache.load_series(series)

        orderbook: OrderbookSnapshot | None = None
        if config.fetch_orderbook:
            orderbook = self.rest_client.get_orderbook(config.symbol, limit=config.orderbook_limit)

        candles = {config.base_timeframe: cache_base_series, **synthetic_series}
        snapshot_quality = self._snapshot_quality(cache_quality, rest_quality, synthetic_series, stats)
        snapshot = MarketSnapshot(
            primary_symbol=config.symbol.upper(),
            base_timeframe=config.base_timeframe,
            candles=candles,
            orderbook=orderbook,
            quality=snapshot_quality,
            payload={
                "refresh_type": "rest_reconciliation",
                "reconcile_candles": reconcile_limit,
                "snapshot_candle_limit": snapshot_limit,
                "rest_series_id": rest_series.series_id,
                "cache_base_series_id": cache_base_series.series_id,
                "synthetic_timeframes": config.synthetic_timeframes,
                "cache_series": sorted(candles.keys()),
                "rest_quality": self._quality_summary(rest_quality),
                "cache_quality": self._quality_summary(cache_quality),
                "synthetic_quality": {
                    timeframe: self._quality_summary(series.quality)
                    for timeframe, series in sorted(synthetic_series.items())
                },
                "rest_reconciliation": stats,
            },
        )
        return MarketSnapshotRefreshResult(
            snapshot=snapshot,
            rest_series=rest_series,
            cache_base_series=cache_base_series,
            synthetic_series=synthetic_series,
            reconciled_candle_count=stats["reconciled_candle_count"],
            matched_candle_count=stats["matched_candle_count"],
            filled_candle_count=stats["filled_candle_count"],
            replaced_candle_count=stats["replaced_candle_count"],
            mismatch_open_times=stats["mismatch_open_times"],
        )

    def _apply_rest_reconciliation(
        self,
        rest_series: CandleSeries,
        before_by_open_time: Dict[str, Candle],
    ) -> Dict[str, Any]:
        matched = 0
        filled = 0
        replaced = 0
        mismatch_open_times: List[str] = []
        for rest_candle in rest_series.candles:
            previous = before_by_open_time.get(rest_candle.open_time)
            if previous is None:
                filled += 1
            elif self._ohlcv_matches(previous, rest_candle):
                matched += 1
            else:
                replaced += 1
                mismatch_open_times.append(rest_candle.open_time)
            self.cache.upsert_candle(rest_candle)

        return {
            "reconciled_candle_count": rest_series.count,
            "matched_candle_count": matched,
            "filled_candle_count": filled,
            "replaced_candle_count": replaced,
            "mismatch_count": len(mismatch_open_times),
            "mismatch_open_times": mismatch_open_times[:20],
            "mismatch_open_times_truncated": len(mismatch_open_times) > 20,
        }

    @staticmethod
    def _snapshot_quality(
        cache_quality: DataQualityReport,
        rest_quality: DataQualityReport,
        synthetic_series: Dict[str, CandleSeries],
        stats: Dict[str, Any],
    ) -> DataQualityReport:
        synthetic_scores = [series.quality.score for series in synthetic_series.values()]
        all_scores = [cache_quality.score, rest_quality.score, *synthetic_scores]
        score = min(all_scores) if all_scores else 0.0
        issue_codes = [*rest_quality.issue_codes, *cache_quality.issue_codes]
        for timeframe, series in synthetic_series.items():
            issue_codes.extend(f"{timeframe}:{code}" for code in series.quality.issue_codes)

        return DataQualityReport(
            is_usable=rest_quality.is_usable and cache_quality.is_usable and score > 0.0,
            score=score,
            completeness=min(rest_quality.completeness, cache_quality.completeness),
            gap_count=rest_quality.gap_count + cache_quality.gap_count,
            issue_codes=issue_codes,
            notes=["REST/cache mismatches were reconciled."] if stats["mismatch_count"] else [],
            payload={
                "rest_quality_score": rest_quality.score,
                "cache_quality_score": cache_quality.score,
                "synthetic_scores": synthetic_scores,
                "rest_cache_mismatch_count": stats["mismatch_count"],
            },
        )

    @staticmethod
    def _quality_summary(quality: DataQualityReport) -> Dict[str, Any]:
        return {
            "quality_score": quality.score,
            "quality_usable": quality.is_usable,
            "completeness": quality.completeness,
            "gap_count": quality.gap_count,
            "issue_codes": quality.issue_codes,
            "payload": quality.payload,
        }

    @staticmethod
    def _ohlcv_matches(left: Candle, right: Candle) -> bool:
        return (
            left.open == right.open
            and left.high == right.high
            and left.low == right.low
            and left.close == right.close
            and left.volume == right.volume
            and left.quote_volume == right.quote_volume
            and left.trade_count == right.trade_count
            and left.taker_buy_base_volume == right.taker_buy_base_volume
            and left.taker_buy_quote_volume == right.taker_buy_quote_volume
        )
