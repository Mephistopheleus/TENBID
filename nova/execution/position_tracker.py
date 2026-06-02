"""Position tracking facade over PositionManager.

PositionManager owns exchange position lifecycle. This tracker keeps the older
module boundary usable without creating a second position owner.
"""

from __future__ import annotations

from nova.execution.position_manager import ExchangePosition, PositionManager, PositionManagementResult
from nova.risk.models import RiskDecision


class PositionTracker:
    def __init__(self, manager: PositionManager) -> None:
        self.manager = manager

    def current_position(self, symbol: str) -> ExchangePosition | None:
        return self.manager.current_position(symbol)

    def update(self, *, risk_decision: RiskDecision) -> list[PositionManagementResult]:
        return self.manager.manage_open_records(risk_decision=risk_decision)
