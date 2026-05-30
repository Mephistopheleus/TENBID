"""Binance Futures connector skeleton.

Chooses TESTNET or LIVE endpoint from immutable secrets config.
"""

class BinanceFuturesConnector:
    async def connect(self) -> None:
        raise NotImplementedError

    async def place_order(self, order: object) -> object:
        raise NotImplementedError

