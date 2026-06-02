"""Append-only outcome recorder for runtime, shadow and lab scenarios.

This module records traceable facts. It does not decide, approve execution,
change confidence, or tune parameters.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional

from nova.autotune.models import AutotuneEvidence
from nova.core.events import Event, EventTypes
from nova.core.history_db import HistoryDB
from nova.decision.trade_plan import TradePlan
from nova.execution.models import ExecutionAttempt, ExecutorResultStatus
from nova.risk.models import RiskDecision
from nova.shadow.outcome import OutcomeResult, ResolutionMethod, ScenarioOutcome
from nova.shadow.scenario import ScenarioRequest, ScenarioSource


class OutcomeRecorder:
    def __init__(self, history_db: HistoryDB) -> None:
        self.history_db = history_db

    def record_execution_ack(
        self,
        *,
        run_id: str,
        cycle_id: str,
        scenario_id: str,
        plan: TradePlan,
        risk_decision: RiskDecision,
        attempt: ExecutionAttempt,
        evidence: AutotuneEvidence,
    ) -> tuple[ScenarioOutcome, Event]:
        result = self._execution_result(attempt)
        quality = 1.0 if attempt.result.status == ExecutorResultStatus.ACCEPTED else 0.8
        outcome = ScenarioOutcome(
            scenario_id=scenario_id,
            source_type=ScenarioSource.REAL_EXECUTION,
            result=result,
            gross_pnl_pct=0.0,
            net_pnl_pct=0.0,
            mfe_pct=0.0,
            mae_pct=0.0,
            duration_sec=0,
            resolution_method=ResolutionMethod.EXECUTION_ACK,
            quality=quality,
            planned_costs=self._planned_costs(plan),
            actual_costs={},
            payload=self._plan_payload(plan),
            notes="Execution acknowledgement only; position PnL outcome is not resolved here.",
        )
        event = self._persist(
            outcome=outcome,
            run_id=run_id,
            cycle_id=cycle_id,
            source="OutcomeRecorder",
            payload_extra={
                "plan_id": plan.plan_id,
                "risk_decision_id": risk_decision.risk_decision_id,
                "executor_result_id": attempt.result.result_id,
                "autotune_evidence_id": evidence.evidence_id,
                "traceable_outcome_sample_count": self.history_db.count_traceable_outcomes(),
                "position_outcome_resolved": False,
            },
        )
        return outcome, event

    def record_shadow_placeholder(
        self,
        *,
        run_id: str,
        cycle_id: str,
        request: ScenarioRequest,
        plan: TradePlan,
        risk_decision: RiskDecision,
        evidence: AutotuneEvidence,
    ) -> tuple[ScenarioOutcome, Event]:
        outcome = ScenarioOutcome(
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
            planned_costs=self._planned_costs(plan),
            actual_costs={},
            payload={
                **self._plan_payload(plan),
                "evaluation_window_min": request.evaluation_window_min,
                "parameter_variant": request.parameter_variant,
                "tags": request.tags,
            },
            notes="Shadow request recorded; market-resolution engine has not resolved outcome yet.",
        )
        event = self._persist(
            outcome=outcome,
            run_id=run_id,
            cycle_id=cycle_id,
            source="OutcomeRecorder",
            payload_extra={
                "plan_id": plan.plan_id,
                "risk_decision_id": risk_decision.risk_decision_id,
                "shadow_source_id": request.source_id,
                "autotune_evidence_id": evidence.evidence_id,
                "traceable_outcome_sample_count": self.history_db.count_traceable_outcomes(),
                "traceable": False,
            },
        )
        return outcome, event

    def record_testnet_close(
        self,
        *,
        run_id: str,
        cycle_id: str,
        scenario_id: str,
        plan: TradePlan,
        entry_attempt: ExecutionAttempt,
        close_attempt: ExecutionAttempt,
        risk_decision: RiskDecision,
        evidence: AutotuneEvidence,
    ) -> tuple[ScenarioOutcome, Event]:
        gross_pnl_pct = self._testnet_pnl_pct(plan, entry_attempt, close_attempt)
        result = OutcomeResult.OBSERVED_FLAT
        if gross_pnl_pct > 0:
            result = OutcomeResult.OBSERVED_WIN
        elif gross_pnl_pct < 0:
            result = OutcomeResult.OBSERVED_LOSS
        close_accepted = close_attempt.result.status == ExecutorResultStatus.ACCEPTED
        outcome = ScenarioOutcome(
            scenario_id=scenario_id,
            source_type=ScenarioSource.REAL_EXECUTION,
            result=result if close_accepted else OutcomeResult.UNRESOLVED,
            gross_pnl_pct=gross_pnl_pct,
            net_pnl_pct=gross_pnl_pct - float(self._planned_costs(plan).get("total_cost_pct", 0.0)),
            mfe_pct=max(0.0, gross_pnl_pct),
            mae_pct=min(0.0, gross_pnl_pct),
            duration_sec=0,
            resolution_method=ResolutionMethod.TESTNET_CLOSE if close_accepted else ResolutionMethod.AMBIGUOUS,
            quality=1.0 if close_accepted else 0.0,
            planned_costs=self._planned_costs(plan),
            actual_costs={},
            payload={
                **self._plan_payload(plan),
                "entry_result_id": entry_attempt.result.result_id,
                "entry_exchange_order_id": entry_attempt.result.exchange_order_id,
                "entry_avg_price": entry_attempt.result.avg_price,
                "close_result_id": close_attempt.result.result_id,
                "close_exchange_order_id": close_attempt.result.exchange_order_id,
                "close_avg_price": close_attempt.result.avg_price,
                "close_status": close_attempt.result.status,
            },
            notes="TESTNET reduce-only close outcome." if close_accepted else "TESTNET close attempt did not produce a resolved outcome.",
        )
        event = self._persist(
            outcome=outcome,
            run_id=run_id,
            cycle_id=cycle_id,
            source="OutcomeRecorder",
            payload_extra={
                "plan_id": plan.plan_id,
                "risk_decision_id": risk_decision.risk_decision_id,
                "entry_executor_result_id": entry_attempt.result.result_id,
                "close_executor_result_id": close_attempt.result.result_id,
                "autotune_evidence_id": evidence.evidence_id,
                "position_outcome_resolved": close_accepted,
            },
        )
        return outcome, event

    def record_position_manager_close(
        self,
        *,
        run_id: str,
        cycle_id: str,
        scenario_id: str,
        plan: TradePlan,
        entry_attempt: ExecutionAttempt,
        close_attempt: ExecutionAttempt,
        risk_decision: RiskDecision,
        evidence: AutotuneEvidence,
        close_reason: str,
        position_payload: dict[str, Any],
    ) -> tuple[ScenarioOutcome, Event]:
        gross_pnl_pct = self._testnet_pnl_pct(plan, entry_attempt, close_attempt)
        result = OutcomeResult.OBSERVED_FLAT
        if gross_pnl_pct > 0:
            result = OutcomeResult.OBSERVED_WIN
        elif gross_pnl_pct < 0:
            result = OutcomeResult.OBSERVED_LOSS
        close_accepted = close_attempt.result.status == ExecutorResultStatus.ACCEPTED
        outcome = ScenarioOutcome(
            scenario_id=scenario_id,
            source_type=ScenarioSource.REAL_EXECUTION,
            result=result if close_accepted else OutcomeResult.UNRESOLVED,
            gross_pnl_pct=gross_pnl_pct,
            net_pnl_pct=gross_pnl_pct - float(self._planned_costs(plan).get("total_cost_pct", 0.0)),
            mfe_pct=max(0.0, gross_pnl_pct),
            mae_pct=min(0.0, gross_pnl_pct),
            duration_sec=0,
            resolution_method=ResolutionMethod.POSITION_MANAGER_CLOSE if close_accepted else ResolutionMethod.AMBIGUOUS,
            quality=1.0 if close_accepted else 0.0,
            planned_costs=self._planned_costs(plan),
            actual_costs={},
            payload={
                **self._plan_payload(plan),
                "entry_result_id": entry_attempt.result.result_id,
                "entry_exchange_order_id": entry_attempt.result.exchange_order_id,
                "entry_avg_price": entry_attempt.result.avg_price,
                "close_result_id": close_attempt.result.result_id,
                "close_exchange_order_id": close_attempt.result.exchange_order_id,
                "close_avg_price": close_attempt.result.avg_price,
                "close_status": close_attempt.result.status,
                "close_reason": close_reason,
                "position_manager": position_payload,
            },
            notes="PositionManager resolved position outcome." if close_accepted else "PositionManager close did not resolve the position outcome.",
        )
        event = self._persist(
            outcome=outcome,
            run_id=run_id,
            cycle_id=cycle_id,
            source="OutcomeRecorder",
            payload_extra={
                "plan_id": plan.plan_id,
                "risk_decision_id": risk_decision.risk_decision_id,
                "entry_executor_result_id": entry_attempt.result.result_id,
                "close_executor_result_id": close_attempt.result.result_id,
                "autotune_evidence_id": evidence.evidence_id,
                "position_outcome_resolved": close_accepted,
                "position_manager_close_reason": close_reason,
            },
        )
        return outcome, event

    def _persist(
        self,
        *,
        outcome: ScenarioOutcome,
        run_id: str,
        cycle_id: str,
        source: str,
        payload_extra: Optional[dict[str, Any]] = None,
    ) -> Event:
        self.history_db.log_scenario_outcome(outcome)
        payload = {
            **asdict(outcome),
            **(payload_extra or {}),
            "traceable_outcome_sample_count": self.history_db.count_traceable_outcomes(),
        }
        return Event(
            event_type=EventTypes.SCENARIO_OUTCOME_RECORDED,
            run_id=run_id,
            cycle_id=cycle_id,
            source=source,
            payload=payload,
        )

    @staticmethod
    def _execution_result(attempt: ExecutionAttempt) -> str:
        if attempt.result.status == ExecutorResultStatus.ACCEPTED:
            return OutcomeResult.EXECUTOR_ACCEPTED
        if attempt.result.status == ExecutorResultStatus.NOT_CALLED:
            return OutcomeResult.EXECUTOR_NOT_CALLED
        return OutcomeResult.EXECUTOR_REJECTED

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

    @staticmethod
    def _plan_payload(plan: TradePlan) -> dict[str, Any]:
        return {
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
        }

    @staticmethod
    def _testnet_pnl_pct(plan: TradePlan, entry_attempt: ExecutionAttempt, close_attempt: ExecutionAttempt) -> float:
        entry_price = entry_attempt.result.avg_price or plan.entry_price
        close_price = close_attempt.result.avg_price
        if entry_price is None or close_price is None or entry_price <= 0:
            return 0.0
        if plan.decision == "PREPARE_SHORT":
            return (entry_price - close_price) / entry_price * 100
        return (close_price - entry_price) / entry_price * 100
