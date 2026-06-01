"""Runtime reports for real execution slices.

Reporter does not decide, validate or invent outcomes. It only packages the
already-created real runtime artifacts into one auditable event.
"""

from __future__ import annotations

from typing import Any, Optional

from nova.core.ids import new_id
from nova.decision.trade_plan import TradePlan
from nova.execution.models import ExecutionAttempt
from nova.risk.models import RiskDecision


class Reporter:
    def generate_execution_report(
        self,
        *,
        plan: TradePlan,
        risk_decision: RiskDecision,
        attempt: ExecutionAttempt,
        shadow_request: Optional[object] = None,
        lab_request: Optional[object] = None,
        autotune_evidence: Optional[object] = None,
    ) -> dict[str, Any]:
        return {
            "report_id": new_id("REPORT"),
            "report_type": "TESTNET_EXECUTION_REPORT",
            "fake_outcome": False,
            "outcome_status": "execution_report_only_position_outcome_not_recorded",
            "plan": {
                "plan_id": plan.plan_id,
                "decision": plan.decision,
                "symbol": plan.symbol,
                "confidence": plan.confidence,
                "analyzer_probability": plan.dynamics_summary.get("analyzer_probability"),
                "autotuner_trust_points": plan.dynamics_summary.get("autotuner_trust_points"),
                "entry_price": plan.entry_price,
                "stop_loss": plan.stop_loss,
                "take_profit": plan.take_profit,
                "net_expected_edge_pct": plan.net_expected_edge_pct,
                "rr_ratio": plan.rr_ratio,
                "forecast_matrix_id": plan.forecast_matrix_id,
                "state_matrix_id": plan.state_matrix_id,
            },
            "risk": {
                "risk_decision_id": risk_decision.risk_decision_id,
                "status": risk_decision.status,
                "reason": risk_decision.reason,
                "approved_for_executor": risk_decision.approved_for_executor,
                "warnings": risk_decision.warnings,
                "hard_blocks": risk_decision.hard_blocks,
            },
            "execution": {
                "request_id": attempt.request.request_id if attempt.request else None,
                "result_id": attempt.result.result_id,
                "status": attempt.result.status,
                "reason": attempt.result.reason,
                "exchange_order_id": attempt.result.exchange_order_id,
                "client_order_id": attempt.result.client_order_id,
                "executed_qty": attempt.result.executed_qty,
                "avg_price": attempt.result.avg_price,
                "raw_response": attempt.result.raw_response,
            },
            "shadow": self._request_ref(shadow_request),
            "lab": self._request_ref(lab_request),
            "autotune": {
                "evidence_id": getattr(autotune_evidence, "evidence_id", None),
                "source_type": getattr(autotune_evidence, "source_type", None),
                "source_weight": getattr(autotune_evidence, "source_weight", None),
            },
        }

    @staticmethod
    def _request_ref(request: Optional[object]) -> Optional[dict[str, Any]]:
        if request is None:
            return None
        return {
            "scenario_id": getattr(request, "scenario_id", None),
            "source_type": getattr(request, "source_type", None),
            "source_id": getattr(request, "source_id", None),
            "trade_plan_id": getattr(request, "trade_plan_id", None),
            "tags": getattr(request, "tags", None),
        }
