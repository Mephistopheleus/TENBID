"""Intrabar resolver for ambiguous 5m candles.

Uses 1m or aggTrades replay only when needed.
"""

class IntrabarResolver:
    def resolve(self) -> object:
        raise NotImplementedError

