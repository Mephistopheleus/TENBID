"""Rolling candle cache.

Analyzers and matrix layers read from cache, not directly from Binance.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from nova.data.models import Candle, CandleSeries, DataQualityReport, DataSourceRef, DataSourceType


class CandleCache:
    def __init__(self, max_candles_per_series: int = 1000) -> None:
        self.max_candles_per_series = max_candles_per_series
        self._candles: Dict[Tuple[str, str], List[Candle]] = {}

    def load_series(self, series: CandleSeries) -> None:
        self._candles[(series.symbol, series.timeframe)] = list(series.candles)[-self.max_candles_per_series :]

    def update_from_kline(self, kline: Candle) -> None:
        self.upsert_candle(kline)

    def upsert_candle(self, candle: Candle) -> None:
        key = (candle.symbol, candle.timeframe)
        candles = self._candles.setdefault(key, [])
        for index, existing in enumerate(candles):
            if existing.open_time == candle.open_time:
                candles[index] = candle
                break
        else:
            candles.append(candle)
        candles.sort(key=lambda item: item.open_time)
        del candles[:-self.max_candles_per_series]

    def get_series(self, symbol: str, timeframe: str, limit: int | None = None) -> CandleSeries:
        symbol = symbol.upper()
        candles = list(self._candles.get((symbol, timeframe), []))
        if limit is not None:
            candles = candles[-limit:]
        source = DataSourceRef(
            source_type=DataSourceType.INTERNAL,
            source_id="candle_cache",
            symbol=symbol,
            timeframe=timeframe,
            payload={"limit": limit},
        )
        return CandleSeries(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            source=source,
            quality=DataQualityReport(is_usable=bool(candles), score=1.0 if candles else 0.0),
        )

    def get_closed(self, timeframe: str, limit: int, symbol: str) -> CandleSeries:
        series = self.get_series(symbol=symbol, timeframe=timeframe)
        closed = [candle for candle in series.candles if candle.is_closed][-limit:]
        return CandleSeries(symbol=symbol.upper(), timeframe=timeframe, candles=closed, source=series.source, quality=series.quality)

    def latest_closed(self, symbol: str, timeframe: str) -> Candle | None:
        return self.get_closed(timeframe=timeframe, limit=1, symbol=symbol).latest_closed()
