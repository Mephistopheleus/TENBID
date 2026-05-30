"""Immutable safety boundaries.

Autotuner may tune working parameters, but SafetyKernel defines what must never be crossed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyPolicy:
    allowed_symbol: str = "DOGEUSDT"
    allowed_mode: str = "TESTNET"
    live_requires_unlock: bool = True
    require_stop_loss: bool = True
    max_concurrent_positions: int = 1


class SafetyKernel:
    def __init__(self, policy: SafetyPolicy | None = None) -> None:
        self.policy = policy or SafetyPolicy()

    def assert_mode_allowed(self, mode: str, live_unlock: bool = False) -> None:
        if mode == "LIVE" and (self.policy.live_requires_unlock and not live_unlock):
            raise PermissionError("LIVE mode is locked")
        if mode != self.policy.allowed_mode and mode != "LIVE":
            raise PermissionError(f"Mode not allowed: {mode}")

    def assert_symbol_allowed(self, symbol: str) -> None:
        if symbol != self.policy.allowed_symbol:
            raise PermissionError(f"Symbol not allowed: {symbol}")
