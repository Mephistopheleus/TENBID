"""Decision engine facade for scenario-to-plan calculation."""

from __future__ import annotations

from typing import Any

from nova.data.models import MarketSnapshot
from nova.decision.trade_calculator import TradeCalculator, TradeCalculatorConfig
from nova.decision.trade_plan import TradePlan
from nova.scenario.models import ScenarioCandidate


class DecisionEngine:
    def __init__(self, calculator: TradeCalculator | None = None) -> None:
        self.calculator = calculator

    def create_trade_plan(
        self,
        *,
        candidate: ScenarioCandidate | None,
        market_snapshot: MarketSnapshot | None,
        profile_id: str,
        profile_values: dict[str, Any] | None = None,
    ) -> TradePlan:
        calculator = self.calculator or TradeCalculator(TradeCalculatorConfig.from_profile(profile_values or {}))
        return calculator.calculate(candidate=candidate, market_snapshot=market_snapshot, profile_id=profile_id)
