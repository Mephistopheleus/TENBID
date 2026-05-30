"""Tracks open positions, exits and real outcomes."""

class PositionTracker:
    async def update(self) -> object:
        raise NotImplementedError

