"""Risk-layer compatibility facade for the canonical decision TradeCalculator."""

from __future__ import annotations

from nova.decision.trade_calculator import TradeCalculator as DecisionTradeCalculator
from nova.decision.trade_calculator import TradeCalculatorConfig
from nova.decision.trade_plan import TradePlan
from nova.data.models import MarketSnapshot
from nova.scenario.models import ScenarioCandidate


class TradeCalculator:
    def __init__(self, config: TradeCalculatorConfig | None = None) -> None:
        self._calculator = DecisionTradeCalculator(config)

    def calculate_candidate(
        self,
        *,
        candidate: ScenarioCandidate | None,
        market_snapshot: MarketSnapshot | None,
        profile_id: str,
    ) -> TradePlan:
        return self._calculator.calculate(
            candidate=candidate,
            market_snapshot=market_snapshot,
            profile_id=profile_id,
        )
