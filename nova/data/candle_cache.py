"""Rolling candle cache.

Analyzers and matrix layers read from cache, not directly from Binance.
"""

class CandleCache:
    def update_from_kline(self, kline: object) -> None:
        raise NotImplementedError

    def get_closed(self, timeframe: str, limit: int) -> object:
        raise NotImplementedError

