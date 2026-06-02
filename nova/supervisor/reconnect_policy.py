"""Reconnect/backfill policy used by websocket runtime loops."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReconnectDecision:
    should_reconnect: bool
    backoff_sec: float
    reason: str
    attempt_number: int


class ReconnectPolicy:
    def __init__(self, *, max_reconnects: int = 2, backoff_sec: float = 1.0) -> None:
        self.max_reconnects = max(0, int(max_reconnects))
        self.backoff_sec = max(0.0, float(backoff_sec))

    def on_disconnect(self, *, attempt_number: int, reason: str = "disconnect") -> ReconnectDecision:
        should_reconnect = attempt_number < self.max_reconnects
        return ReconnectDecision(
            should_reconnect=should_reconnect,
            backoff_sec=self.backoff_sec if should_reconnect else 0.0,
            reason=reason if should_reconnect else "max_reconnects_reached",
            attempt_number=attempt_number,
        )
