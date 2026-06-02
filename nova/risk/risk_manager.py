"""Risk manager for calculated TradePlans.

In TESTNET this layer is not a fear brake. It keeps hard-invalid plans away
from the executor and marks weak-but-useful plans as warning-rich evidence for
Shadow, Laboratory and Autotuner.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from nova.decision.trade_plan import PlanRole, TradePlan
from nova.matrix.models import StateMatrix
from nova.risk.models import RiskDecision, RiskDecisionStatus


class RiskManager:
    def evaluate(
        self,
        *,
        plan: TradePlan,
        state_matrix: Optional[StateMatrix],
        profile_values: Dict[str, Any],
        active_positions_count: int = 0,
    ) -> RiskDecision:
        hard_blocks: list[str] = []
        warnings: list[str] = []

        if plan.decision == "HOLD":
            hard_blocks.append("plan_is_hold")
        if plan.plan_role != PlanRole.CALCULATED:
            hard_blocks.append("plan_not_calculated")
        if plan.entry_price is None or plan.entry_price <= 0.0:
            hard_blocks.append("missing_entry_price")
        if plan.stop_loss is None or plan.stop_loss <= 0.0:
            hard_blocks.append("missing_invalidation_boundary")
        if plan.take_profit is None or plan.take_profit <= 0.0:
            hard_blocks.append("missing_target_price")
        if not plan.forecast_matrix_id:
            hard_blocks.append("missing_forecast_matrix_lineage")
        if not plan.state_matrix_id:
            hard_blocks.append("missing_state_matrix_lineage")

        max_positions = int(profile_values.get("max_concurrent_positions", 1))
        if active_positions_count >= max_positions:
            hard_blocks.append("max_concurrent_positions_reached")

        min_edge = float(profile_values.get("min_net_edge_pct", 0.0))
        if plan.net_expected_edge_pct < min_edge:
            warnings.append("net_edge_below_profile_reference")

        target_rr_min = float(profile_values.get("target_rr_min", 0.0))
        if plan.rr_ratio is not None and plan.rr_ratio < target_rr_min:
            warnings.append("rr_below_profile_reference")

        execution_blocking_enabled = bool(profile_values.get("execution_blocking_enabled", True))
        confidence_threshold = float(profile_values.get("confidence_threshold", 0.7))
        if plan.confidence < confidence_threshold:
            if execution_blocking_enabled:
                hard_blocks.append("effective_confidence_below_profile_threshold")
            else:
                warnings.append("effective_confidence_below_profile_threshold")

        minimum_shadow_samples = int(profile_values.get("minimum_shadow_samples_before_execution", 50))
        shadow_sample_count = int(profile_values.get("shadow_outcome_sample_count", 0))
        if shadow_sample_count < minimum_shadow_samples:
            if execution_blocking_enabled:
                hard_blocks.append("minimum_shadow_samples_not_reached")
            else:
                warnings.append("minimum_shadow_samples_not_reached")

        if state_matrix is None:
            warnings.append("missing_state_matrix_object")
        else:
            if state_matrix.liquidity_state != "orderbook_available":
                warnings.append(f"liquidity_state_{state_matrix.liquidity_state}")
            if state_matrix.payload.get("recheck_reasons"):
                warnings.append("state_matrix_recheck_reasons_present")

        calculator_flags = plan.dynamics_summary.get("calculator_flags")
        if isinstance(calculator_flags, dict):
            warnings.extend(str(name) for name, active in calculator_flags.items() if active is True)

        warnings = sorted(set(warnings))
        if hard_blocks:
            hard_blocks = sorted(set(hard_blocks))
            shadow_first = "minimum_shadow_samples_not_reached" in hard_blocks
            return RiskDecision(
                plan_id=plan.plan_id,
                status=RiskDecisionStatus.SHADOW_FIRST_REQUIRED if shadow_first else RiskDecisionStatus.REJECTED,
                reason="shadow_outcome_minimum_not_reached" if shadow_first else "hard_risk_blocks_present",
                approved_for_executor=False,
                profile_id=plan.profile_id,
                state_matrix_id=plan.state_matrix_id,
                warnings=warnings,
                hard_blocks=hard_blocks,
                payload=self._payload(plan, state_matrix, profile_values, active_positions_count),
            )

        status = RiskDecisionStatus.APPROVED_WITH_WARNINGS if warnings else RiskDecisionStatus.APPROVED
        return RiskDecision(
            plan_id=plan.plan_id,
            status=status,
            reason="testnet_plan_admissible_with_recorded_warnings" if warnings else "testnet_plan_admissible",
            approved_for_executor=True,
            profile_id=plan.profile_id,
            state_matrix_id=plan.state_matrix_id,
            warnings=warnings,
            hard_blocks=[],
            adjusted_size_factor=1.0,
            payload=self._payload(plan, state_matrix, profile_values, active_positions_count),
        )

    @staticmethod
    def _payload(
        plan: TradePlan,
        state_matrix: Optional[StateMatrix],
        profile_values: Dict[str, Any],
        active_positions_count: int,
    ) -> Dict[str, object]:
        execution_blocking_enabled = bool(profile_values.get("execution_blocking_enabled", True))
        return {
            "not_executor": True,
            "testnet_feedback_mode": True,
            "decision": plan.decision,
            "plan_role": plan.plan_role,
            "net_expected_edge_pct": plan.net_expected_edge_pct,
            "rr_ratio": plan.rr_ratio,
            "confidence": plan.confidence,
            "analyzer_probability": plan.dynamics_summary.get("analyzer_probability"),
            "autotuner_trust_points": plan.dynamics_summary.get("autotuner_trust_points"),
            "effective_confidence": plan.dynamics_summary.get("effective_confidence", plan.confidence),
            "state_context_trust_score": state_matrix.trust_score if state_matrix else None,
            "state_liquidity_state": state_matrix.liquidity_state if state_matrix else None,
            "active_positions_count": active_positions_count,
            "minimum_shadow_samples_before_execution": profile_values.get("minimum_shadow_samples_before_execution", 50),
            "shadow_outcome_sample_count": profile_values.get("shadow_outcome_sample_count", 0),
            "execution_blocking_enabled": execution_blocking_enabled,
            "profile_refs": {
                "min_net_edge_pct": profile_values.get("min_net_edge_pct"),
                "target_rr_min": profile_values.get("target_rr_min"),
                "confidence_threshold": profile_values.get("confidence_threshold"),
                "max_concurrent_positions": profile_values.get("max_concurrent_positions"),
            },
        }
