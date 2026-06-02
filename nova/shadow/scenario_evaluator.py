"""Single outcome builder for shadow, laboratory and alternative scenarios."""

from __future__ import annotations

from nova.decision.trade_plan import TradePlan
from nova.shadow.outcome import OutcomeResult, ResolutionMethod, ScenarioOutcome
from nova.shadow.scenario import ScenarioRequest


class ScenarioEvaluator:
    def evaluate(self, request: ScenarioRequest, *, plan: TradePlan) -> ScenarioOutcome:
        planned_costs = self._planned_costs(plan)
        return ScenarioOutcome(
            scenario_id=request.scenario_id,
            source_type=request.source_type,
            result=OutcomeResult.PENDING,
            gross_pnl_pct=0.0,
            net_pnl_pct=0.0,
            mfe_pct=0.0,
            mae_pct=0.0,
            duration_sec=0,
            resolution_method=ResolutionMethod.PENDING,
            quality=0.0,
            planned_costs=planned_costs,
            actual_costs={},
            payload={
                "plan_id": plan.plan_id,
                "decision": plan.decision,
                "symbol": plan.symbol,
                "entry_price": plan.entry_price,
                "stop_loss": plan.stop_loss,
                "take_profit": plan.take_profit,
                "rr_ratio": plan.rr_ratio,
                "confidence": plan.confidence,
                "net_expected_edge_pct": plan.net_expected_edge_pct,
                "horizon_min": plan.dynamics_summary.get("horizon_min"),
                "analyzer_probability": plan.dynamics_summary.get("analyzer_probability"),
                "autotuner_trust_points": plan.dynamics_summary.get("autotuner_trust_points"),
                "effective_confidence": plan.dynamics_summary.get("effective_confidence", plan.confidence),
                "recheck_required": plan.dynamics_summary.get("recheck_required"),
                "calculator_flags": plan.dynamics_summary.get("calculator_flags"),
                "evaluation_window_min": request.evaluation_window_min,
                "parameter_variant": request.parameter_variant,
                "tags": request.tags,
                "scenario_request_source_id": request.source_id,
            },
            notes="Scenario request recorded for market-path resolution.",
        )

    @staticmethod
    def _planned_costs(plan: TradePlan) -> dict[str, float]:
        if plan.costs is None:
            return {}
        return {
            "commission_pct": plan.costs.commission_pct,
            "spread_pct": plan.costs.spread_pct,
            "slippage_pct": plan.costs.slippage_pct,
            "total_cost_pct": plan.costs.total_cost_pct,
            "breakeven_move_pct": plan.costs.breakeven_move_pct,
        }
