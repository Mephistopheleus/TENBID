"""Builds synthetic higher timeframe candles from a base CandleSeries."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterable, List

from nova.data.models import Candle, CandleSeries, DataQualityReport, DataSourceRef, DataSourceType


class SyntheticTimeframeBuilder:
    def __init__(self, target_timeframes: Iterable[str] | None = None) -> None:
        self.target_timeframes = list(target_timeframes or ["10m", "15m", "30m", "1h", "4h", "8h", "12h"])

    def build_all(self, base_series: CandleSeries) -> Dict[str, CandleSeries]:
        return {timeframe: self.build(base_series, timeframe) for timeframe in self.target_timeframes}

    def build(self, base_series: CandleSeries, target_timeframe: str) -> CandleSeries:
        base_minutes = timeframe_to_minutes(base_series.timeframe)
        target_minutes = timeframe_to_minutes(target_timeframe)
        if target_minutes <= base_minutes or target_minutes % base_minutes != 0:
            raise ValueError(f"Target timeframe {target_timeframe} must be a multiple of {base_series.timeframe}")
        expected_bucket_size = target_minutes // base_minutes
        buckets: Dict[int, List[Candle]] = defaultdict(list)
        for candle in base_series.candles:
            bucket = int(_parse_iso(candle.open_time).timestamp() // (target_minutes * 60))
            buckets[bucket].append(candle)
        source = DataSourceRef(
            source_type=DataSourceType.SYNTHETIC,
            source_id="synthetic_timeframe_builder",
            symbol=base_series.symbol,
            timeframe=target_timeframe,
            payload={
                "base_timeframe": base_series.timeframe,
                "base_series_id": base_series.series_id,
                "dependency_group": "ohlcv_resampled",
            },
        )
        full_buckets = [(bucket, items) for bucket, items in sorted(buckets.items()) if len(items) == expected_bucket_size]
        skipped_partial_buckets = len(buckets) - len(full_buckets)
        synthetic = [
            self._aggregate_bucket(base_series.symbol, target_timeframe, source, items)
            for _, items in full_buckets
        ]
        return CandleSeries(
            symbol=base_series.symbol,
            timeframe=target_timeframe,
            candles=synthetic,
            source=source,
            quality=DataQualityReport(
                is_usable=bool(synthetic),
                score=1.0 if synthetic else 0.0,
                issue_codes=["partial_synthetic_buckets_skipped"] if skipped_partial_buckets else [],
                payload={"skipped_partial_buckets": skipped_partial_buckets},
            ),
            payload={
                "dependency_group": "ohlcv_resampled",
                "expected_bucket_size": expected_bucket_size,
                "skipped_partial_buckets": skipped_partial_buckets,
            },
        )

    @staticmethod
    def _aggregate_bucket(symbol: str, timeframe: str, source: DataSourceRef, candles: List[Candle]) -> Candle:
        ordered = sorted(candles, key=lambda item: item.open_time)
        return Candle(
            symbol=symbol,
            timeframe=timeframe,
            open_time=ordered[0].open_time,
            close_time=ordered[-1].close_time,
            open=ordered[0].open,
            high=max(item.high for item in ordered),
            low=min(item.low for item in ordered),
            close=ordered[-1].close,
            volume=sum(item.volume for item in ordered),
            quote_volume=_sum_optional(item.quote_volume for item in ordered),
            trade_count=_sum_optional(item.trade_count for item in ordered),
            taker_buy_base_volume=_sum_optional(item.taker_buy_base_volume for item in ordered),
            taker_buy_quote_volume=_sum_optional(item.taker_buy_quote_volume for item in ordered),
            source=source,
            is_closed=all(item.is_closed for item in ordered),
            payload={"source_candle_ids": [item.candle_id for item in ordered]},
        )


def timeframe_to_minutes(timeframe: str) -> int:
    unit = timeframe[-1]
    value = int(timeframe[:-1])
    if unit == "m":
        return value
    if unit == "h":
        return value * 60
    if unit == "d":
        return value * 60 * 24
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _sum_optional(values: Iterable[float | int | None]) -> float | int | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present)
