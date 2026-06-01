"""Online shadow engine.

Creates ScenarioRequest from current plans and risk decisions. It never executes
counterfactual plans.
"""

from __future__ import annotations

from nova.shadow.scenario import ScenarioRequest, ScenarioSource


class ShadowEngine:
    def on_trade_plan(self, trade_plan: object, risk_decision: object) -> ScenarioRequest:
        if getattr(risk_decision, "approved_for_executor", False):
            source_type = ScenarioSource.SHADOW_ALTERNATIVE
            tags = {"purpose": "alternative_management_check"}
        else:
            source_type = ScenarioSource.SHADOW_FORBIDDEN
            tags = {"purpose": "blocked_plan_check"}
        return ScenarioRequest(
            source_type=source_type,
            source_id=getattr(risk_decision, "risk_decision_id", "unknown_risk_decision"),
            symbol=getattr(trade_plan, "symbol", "UNKNOWN"),
            trade_plan_id=getattr(trade_plan, "plan_id", None),
            episode_id=None,
            evaluation_window_min=int(getattr(trade_plan, "dynamics_summary", {}).get("horizon_min", 15)),
            parameter_variant={"source": "runtime_trade_plan"},
            tags=tags,
        )
