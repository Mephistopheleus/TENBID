"""TradePlan calculator for NOVA scenario candidates.

The calculator turns a bounded scenario into a calculable TradePlan. It does not
own market perception, risk approval or execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from nova.data.models import MarketSnapshot
from nova.decision.trade_plan import CostEstimate, PlanRole, TradePlan
from nova.scenario.models import ScenarioCandidate


class CalculatedDecision:
    HOLD = "HOLD"
    PREPARE_LONG = "PREPARE_LONG"
    PREPARE_SHORT = "PREPARE_SHORT"


@dataclass(frozen=True)
class TradeCalculatorConfig:
    min_net_edge_pct: float = 0.12
    sl_min_pct: float = 0.30
    sl_max_pct: float = 2.50
    target_rr_min: float = 1.20
    target_rr_max: float = 3.00
    commission_pct: float = 0.08
    spread_pct: float = 0.02
    slippage_pct: float = 0.05
    entry_offset_pct: float = 0.02
    trailing_activation_pct: float = 0.50

    @classmethod
    def from_profile(cls, values: Dict[str, Any]) -> "TradeCalculatorConfig":
        return cls(
            min_net_edge_pct=float(values.get("min_net_edge_pct", cls.min_net_edge_pct)),
            sl_min_pct=float(values.get("sl_min_pct", cls.sl_min_pct)),
            sl_max_pct=float(values.get("sl_max_pct", cls.sl_max_pct)),
            target_rr_min=float(values.get("target_rr_min", cls.target_rr_min)),
            target_rr_max=float(values.get("target_rr_max", cls.target_rr_max)),
            commission_pct=float(values.get("commission_pct", cls.commission_pct)),
            spread_pct=float(values.get("spread_pct", cls.spread_pct)),
            slippage_pct=float(values.get("slippage_pct", cls.slippage_pct)),
            entry_offset_pct=float(values.get("entry_offset_pct", cls.entry_offset_pct)),
            trailing_activation_pct=float(values.get("trailing_activation_pct", cls.trailing_activation_pct)),
        )


class TradeCalculator:
    def __init__(self, config: TradeCalculatorConfig | None = None) -> None:
        self.config = config or TradeCalculatorConfig()

    def calculate(
        self,
        *,
        candidate: ScenarioCandidate | None,
        market_snapshot: MarketSnapshot | None,
        profile_id: str,
    ) -> TradePlan:
        if candidate is None:
            return self._hold(symbol=market_snapshot.primary_symbol if market_snapshot else "UNKNOWN", profile_id=profile_id, reason="no_scenario_candidate")
        if market_snapshot is None:
            return self._hold(symbol=candidate.symbol, profile_id=profile_id, reason="missing_market_snapshot_for_trade_calculation")

        direction = self._scenario_trade_orientation(candidate)
        if direction is None:
            return self._hold(
                symbol=candidate.symbol,
                profile_id=profile_id,
                reason="scenario_has_no_executor_orientation_yet",
                candidate=candidate,
            )

        entry_price = self._entry_price(candidate.reference_price, direction)
        target_price = self._target_price(candidate, direction)
        invalidation = self._invalidation_boundary(candidate, entry_price, direction)
        risk_pct = self._distance_pct(entry_price, invalidation)
        target_pct = self._distance_pct(entry_price, target_price)
        rr_ratio = target_pct / risk_pct if risk_pct > 0.0 else 0.0
        costs = self._costs()
        gross_edge_pct = target_pct * candidate.probability
        net_edge_pct = gross_edge_pct - costs.total_cost_pct
        effective_confidence = self._effective_confidence(candidate.confidence, candidate.trust_score)

        decision = CalculatedDecision.PREPARE_LONG if direction == "LONG" else CalculatedDecision.PREPARE_SHORT
        reason = "scenario_calculated_for_risk_review"
        flags = self._diagnostic_flags(net_edge_pct=net_edge_pct, rr_ratio=rr_ratio, risk_pct=risk_pct, candidate=candidate)

        return TradePlan(
            decision=decision,
            symbol=candidate.symbol,
            reason=reason,
            profile_id=profile_id,
            plan_role=PlanRole.CALCULATED,
            source_type="RUNTIME_SCENARIO",
            forecast_matrix_id=candidate.forecast_matrix_id,
            state_matrix_id=candidate.state_matrix_id,
            entry_price=entry_price,
            stop_loss=invalidation,
            take_profit=target_price,
            rr_ratio=rr_ratio,
            confidence=effective_confidence,
            net_expected_edge_pct=net_edge_pct,
            costs=costs,
            dynamics_summary={
                "scenario_id": candidate.scenario_id,
                "scenario_type": candidate.scenario_type,
                "scenario_reason": candidate.reason,
                "source_zone_ids": candidate.source_zone_ids,
                "reference_price": candidate.reference_price,
                "price_area": {"low": candidate.price_low, "high": candidate.price_high},
                "horizon_min": candidate.horizon_min,
                "probability": candidate.probability,
                "analyzer_probability": candidate.confidence,
                "autotuner_trust_points": candidate.trust_score,
                "effective_confidence": effective_confidence,
                "effective_confidence_formula": "average(analyzer_probability, autotuner_trust_points)",
                "gross_edge_pct": gross_edge_pct,
                "risk_distance_pct": risk_pct,
                "target_distance_pct": target_pct,
                "recheck_required": candidate.recheck_required,
                "calculator_flags": flags,
                "management_seed": {
                    "trailing_activation_pct": self.config.trailing_activation_pct,
                    "invalidation_boundary": invalidation,
                    "breakeven_move_pct": costs.breakeven_move_pct,
                },
                "not_executed": True,
                "requires_risk_review": True,
            },
        )

    def _scenario_trade_orientation(self, candidate: ScenarioCandidate) -> Optional[str]:
        center = (candidate.price_low + candidate.price_high) / 2.0
        if center > candidate.reference_price:
            return "LONG"
        if center < candidate.reference_price:
            return "SHORT"
        return None

    @staticmethod
    def _effective_confidence(analyzer_probability: float, autotuner_trust_points: float) -> float:
        value = (analyzer_probability + autotuner_trust_points) / 2.0
        return max(0.1, min(0.9, value))

    def _entry_price(self, reference_price: float, direction: str) -> float:
        offset = self.config.entry_offset_pct / 100.0
        if direction == "LONG":
            return reference_price * (1.0 - offset)
        return reference_price * (1.0 + offset)

    @staticmethod
    def _target_price(candidate: ScenarioCandidate, direction: str) -> float:
        return candidate.price_high if direction == "LONG" else candidate.price_low

    def _invalidation_boundary(self, candidate: ScenarioCandidate, entry_price: float, direction: str) -> float:
        if self._candidate_invalidation_is_usable(candidate.invalidation_price, entry_price, direction):
            return float(candidate.invalidation_price)
        distance_pct = self._bounded_risk_distance_pct(candidate)
        if direction == "LONG":
            return entry_price * (1.0 - distance_pct / 100.0)
        return entry_price * (1.0 + distance_pct / 100.0)

    @staticmethod
    def _candidate_invalidation_is_usable(
        invalidation_price: Optional[float],
        entry_price: float,
        direction: str,
    ) -> bool:
        if invalidation_price is None or invalidation_price <= 0.0:
            return False
        if direction == "LONG":
            return invalidation_price < entry_price
        if direction == "SHORT":
            return invalidation_price > entry_price
        return False

    def _bounded_risk_distance_pct(self, candidate: ScenarioCandidate) -> float:
        area_width_pct = ((candidate.price_high - candidate.price_low) / candidate.reference_price) * 100.0
        confidence_adjustment = 1.0 + max(0.0, 0.7 - candidate.confidence)
        raw = max(area_width_pct * confidence_adjustment, self.config.sl_min_pct)
        return min(raw, self.config.sl_max_pct)

    @staticmethod
    def _distance_pct(left: float, right: float) -> float:
        if left <= 0.0:
            return 0.0
        return abs(right - left) / left * 100.0

    def _costs(self) -> CostEstimate:
        total = self.config.commission_pct + self.config.spread_pct + self.config.slippage_pct
        return CostEstimate(
            commission_pct=self.config.commission_pct,
            spread_pct=self.config.spread_pct,
            slippage_pct=self.config.slippage_pct,
            total_cost_pct=total,
            breakeven_move_pct=total,
        )

    def _diagnostic_flags(
        self,
        *,
        net_edge_pct: float,
        rr_ratio: float,
        risk_pct: float,
        candidate: ScenarioCandidate,
    ) -> Dict[str, object]:
        return {
            "net_edge_below_profile_reference": net_edge_pct < self.config.min_net_edge_pct,
            "net_edge_reference_pct": self.config.min_net_edge_pct,
            "risk_distance_above_profile_reference": risk_pct > self.config.sl_max_pct,
            "risk_distance_min_pct": self.config.sl_min_pct,
            "risk_distance_max_pct": self.config.sl_max_pct,
            "rr_below_profile_reference": rr_ratio < self.config.target_rr_min,
            "rr_reference_min": self.config.target_rr_min,
            "rr_reference_max": self.config.target_rr_max,
            "scenario_recheck_required": candidate.recheck_required,
            "requires_risk_manager_decision": True,
        }

    @staticmethod
    def _hold(
        *,
        symbol: str,
        profile_id: str,
        reason: str,
        candidate: ScenarioCandidate | None = None,
    ) -> TradePlan:
        return TradePlan(
            decision=CalculatedDecision.HOLD,
            symbol=symbol,
            reason=reason,
            profile_id=profile_id,
            confidence=0.0,
            net_expected_edge_pct=0.0,
            dynamics_summary={
                "scenario_id": candidate.scenario_id if candidate else None,
                "not_executed": True,
                "requires_risk_review": False,
            },
        )
