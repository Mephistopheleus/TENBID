"""Immutable safety boundaries.

SafetyKernel is a hard guardrail, not a calculator and not an analyzer. It should
only reject states/plans that violate non-negotiable boundaries: mode locks,
allowed symbol and other owner-defined safety invariants.
Autotuner may tune working parameters, but it must not tune these boundaries.

Important separation: dynamic capacity questions belong to RiskManager and
Autotuner. Number/size of independent opportunities depends on balance,
drawdown, remaining funds, risk budget and context quality; it is not a fixed
SafetyKernel limit.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyPolicy:
    """Owner-defined non-tunable boundary set.

    Values here should come from immutable config/policy, not from Autotuner.
    Shadow/Lab may evaluate whether a boundary was useful or too strict, but any
    change to the boundary is an owner decision, not automatic tuning.

    Do not put dynamic risk sizing here. Trades are evaluated independently by
    the calculation/risk layer; portfolio capacity is a tunable risk policy, not
    an immutable safety boundary.
    """

    allowed_symbol: str = "DOGEUSDT"
    allowed_connection: str = "BINANCE_TESTNET"
    live_requires_unlock: bool = True
    require_invalidation_boundary: bool = True


class SafetyKernel:
    def __init__(self, policy: SafetyPolicy | None = None) -> None:
        self.policy = policy or SafetyPolicy()

    def assert_mode_allowed(self, mode: str, live_unlock: bool = False) -> None:
        if mode == "LIVE" and (self.policy.live_requires_unlock and not live_unlock):
            raise PermissionError("LIVE mode is locked")
        if mode not in {"TESTNET", "LIVE"}:
            raise PermissionError(f"Mode not allowed: {mode}")

    def assert_connection_allowed(self, execution_connection: str, live_unlock: bool = False) -> None:
        if execution_connection == "BINANCE_LIVE" and (self.policy.live_requires_unlock and not live_unlock):
            raise PermissionError("BINANCE_LIVE connection is locked")
        if execution_connection != self.policy.allowed_connection and execution_connection != "BINANCE_LIVE":
            raise PermissionError(f"Execution connection not allowed: {execution_connection}")

    def assert_symbol_allowed(self, symbol: str) -> None:
        if symbol != self.policy.allowed_symbol:
            raise PermissionError(f"Symbol not allowed: {symbol}")
