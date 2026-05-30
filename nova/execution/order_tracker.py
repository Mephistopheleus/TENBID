"""Tracks order status and fills from Binance."""

class OrderTracker:
    async def refresh(self) -> object:
        raise NotImplementedError

