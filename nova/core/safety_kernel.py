"""Immutable safety boundaries.

SafetyKernel is a hard guardrail, not a calculator and not an analyzer. It should
only reject states/plans that violate non-negotiable boundaries: mode locks,
allowed symbol, exposure caps and other owner-defined safety invariants.
Autotuner may tune working parameters, but it must not tune these boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyPolicy:
    """Owner-defined non-tunable boundary set.

    Values here should come from immutable config/policy, not from Autotuner.
    Shadow/Lab may evaluate whether a boundary was useful or too strict, but any
    change to the boundary is an owner decision, not automatic tuning.
    """

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
