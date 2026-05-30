"""Builds synthetic 10m/15m/30m/1h/4h candles from base 5m candles."""

class SyntheticTimeframeBuilder:
    def build(self, base_candles: object) -> object:
        raise NotImplementedError

