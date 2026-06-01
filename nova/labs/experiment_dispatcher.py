"""Dispatches lab hypotheses as ScenarioRequest to ScenarioEvaluator."""

from __future__ import annotations

from nova.shadow.scenario import ScenarioRequest, ScenarioSource


class ExperimentDispatcher:
    def dispatch(self, hypothesis: object) -> ScenarioRequest:
        plan = hypothesis.get("trade_plan") if isinstance(hypothesis, dict) else None
        source_id = str(hypothesis.get("source_id", "lab_hypothesis")) if isinstance(hypothesis, dict) else "lab_hypothesis"
        purpose = str(hypothesis.get("purpose", "warning_check")) if isinstance(hypothesis, dict) else "warning_check"
        return ScenarioRequest(
            source_type=ScenarioSource.LAB_EXPERIMENT,
            source_id=source_id,
            symbol=getattr(plan, "symbol", "UNKNOWN"),
            trade_plan_id=getattr(plan, "plan_id", None),
            episode_id=None,
            evaluation_window_min=int(getattr(plan, "dynamics_summary", {}).get("horizon_min", 15)) if plan else 15,
            parameter_variant={"source": "risk_or_execution_warning"},
            tags={"purpose": purpose},
        )
