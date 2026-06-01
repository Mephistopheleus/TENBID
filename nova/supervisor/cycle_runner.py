"""Cycle runner.

CycleRunner stitches data snapshot, state snapshot, analyzers and matrix into a
traceable context package. It is not the market-action calculator; until that
separate layer exists, the runtime finishes with a safe placeholder TradePlan.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List

from nova.analyzers.contracts import AnalysisPackage
from nova.analyzers.market_structure import MarketStructureAnalyzer
from nova.analyzers.registry import AnalyzerRegistry
from nova.analyzers.runner import AnalyzerRunner
from nova.autotune.evidence_collector import EvidenceCollector
from nova.core.config_loader import RuntimeConfig
from nova.core.event_log import EventLog
from nova.core.events import Event, EventTypes
from nova.core.history_db import HistoryDB
from nova.core.ids import CYCLE, new_id
from nova.core.state_snapshot import StateSnapshot, StateSnapshotStage
from nova.data.models import MarketSnapshot
from nova.decision.trade_calculator import TradeCalculator, TradeCalculatorConfig
from nova.decision.trade_plan import TradePlan
from nova.execution.exchange_executor import ExchangeExecutor
from nova.matrix.forecast_matrix import ForecastMatrixEngine
from nova.matrix.models import ForecastMatrix, StateMatrix
from nova.matrix.state_matrix import StateMatrixEngine
from nova.risk.risk_manager import RiskManager
from nova.scenario.builder import ScenarioBuilder
from nova.scenario.models import ScenarioBuildResult
from nova.shadow.shadow_engine import ShadowEngine
from nova.labs.experiment_dispatcher import ExperimentDispatcher


class CycleRunner:
    def __init__(
        self,
        run_id: str,
        config: RuntimeConfig,
        event_log: EventLog,
        history_db: HistoryDB,
        market_snapshot: MarketSnapshot | None = None,
        warmup_error: str | None = None,
    ) -> None:
        self.run_id = run_id
        self.config = config
        self.event_log = event_log
        self.history_db = history_db
        self.market_snapshot = market_snapshot
        self.warmup_error = warmup_error

    def run_once(self) -> TradePlan:
        cycle_id = new_id(CYCLE)
        self._record(
            Event(
                event_type=EventTypes.CYCLE_STARTED,
                run_id=self.run_id,
                cycle_id=cycle_id,
                source="CycleRunner",
                payload={
                    "symbol": self.config.symbol,
                    "profile_id": self.config.profile.profile_id,
                    "market_snapshot_ready": self.market_snapshot is not None,
                    "market_snapshot_id": self.market_snapshot.snapshot_id if self.market_snapshot else None,
                },
            )
        )

        state_snapshot = self._create_pre_decision_state_snapshot(cycle_id)
        self.history_db.log_state_snapshot(state_snapshot)
        self._record(
            Event(
                event_type=EventTypes.STATE_SNAPSHOT_CREATED,
                run_id=self.run_id,
                cycle_id=cycle_id,
                source="CycleRunner",
                payload={
                    "state_snapshot_id": state_snapshot.state_snapshot_id,
                    "run_id": state_snapshot.run_id,
                    "stage": state_snapshot.stage,
                    "symbol": state_snapshot.symbol,
                    "market_snapshot_id": state_snapshot.market_snapshot_id,
                    "training_role": state_snapshot.training_role,
                    "data_quality": state_snapshot.data_quality,
                    "data_usable": state_snapshot.data_usable,
                },
            )
        )

        analysis_summary: Dict[str, Any] = {"status": "not_started"}
        if self.market_snapshot is not None and self.market_snapshot.quality.is_usable:
            analysis_summary = self._run_pre_decision_analysis(cycle_id)

        plan = self._calculate_trade_plan(cycle_id, analysis_summary)
        self.history_db.log_trade_plan(plan, run_id=self.run_id, cycle_id=cycle_id)
        self._record(
            Event(
                event_type=EventTypes.TRADE_PLAN_CREATED,
                run_id=self.run_id,
                cycle_id=cycle_id,
                source="CycleRunner",
                payload={
                    "plan_id": plan.plan_id,
                    "decision": plan.decision,
                    "symbol": plan.symbol,
                    "reason": plan.reason,
                    "profile_id": plan.profile_id,
                    "plan_role": plan.plan_role,
                    "forecast_matrix_id": plan.forecast_matrix_id,
                    "state_matrix_id": plan.state_matrix_id,
                    "net_expected_edge_pct": plan.net_expected_edge_pct,
                    "requires_risk_review": plan.dynamics_summary.get("requires_risk_review"),
                },
            )
        )
        self._run_feedback_slice(cycle_id, plan, analysis_summary)
        return plan

    def _create_pre_decision_state_snapshot(self, cycle_id: str) -> StateSnapshot:
        if self.market_snapshot is None:
            return StateSnapshot(
                symbol=self.config.symbol,
                run_id=self.run_id,
                cycle_id=cycle_id,
                stage=StateSnapshotStage.PRE_DECISION,
                market_snapshot_id=None,
                data_quality=0.0,
                data_usable=False,
                payload={
                    "status": "data_warmup_failed",
                    "warmup_error": self.warmup_error,
                    "training_note": "Context snapshot only; not an outcome label.",
                },
            )

        return StateSnapshot(
            symbol=self.config.symbol,
            run_id=self.run_id,
            cycle_id=cycle_id,
            stage=StateSnapshotStage.PRE_DECISION,
            market_snapshot_id=self.market_snapshot.snapshot_id,
            data_quality=self.market_snapshot.quality.score,
            data_usable=self.market_snapshot.quality.is_usable,
            volatility_state="not_evaluated",
            liquidity_state="not_evaluated" if self.market_snapshot.orderbook is None else "orderbook_snapshot_available",
            scale_state="not_evaluated",
            conflict_score=0.0,
            payload={
                "market_snapshot_created_at": self.market_snapshot.created_at,
                "base_timeframe": self.market_snapshot.base_timeframe,
                "quality_issue_codes": self.market_snapshot.quality.issue_codes,
                "candle_counts": {
                    timeframe: series.count for timeframe, series in sorted(self.market_snapshot.candles.items())
                },
                "training_note": "Context snapshot only; not an outcome label.",
            },
        )

    def _run_pre_decision_analysis(self, cycle_id: str) -> Dict[str, Any]:
        registry = AnalyzerRegistry([MarketStructureAnalyzer()])
        analyzer_names = sorted(registry.manifests().keys())
        self._record(
            Event(
                event_type=EventTypes.ANALYSIS_PASS_STARTED,
                run_id=self.run_id,
                cycle_id=cycle_id,
                source="CycleRunner",
                payload={
                    "stage": "RAW",
                    "symbol": self.config.symbol,
                    "timeframe": self.config.base_timeframe,
                    "market_snapshot_id": self.market_snapshot.snapshot_id if self.market_snapshot else None,
                    "analyzers": analyzer_names,
                },
            )
        )
        try:
            packages = AnalyzerRunner(registry).run_raw_pass(
                run_id=self.run_id,
                cycle_id=cycle_id,
                symbol=self.config.symbol,
                timeframe=self.config.base_timeframe,
                profile_id=self.config.profile.profile_id,
                market_snapshot=self.market_snapshot,
            )
            for package in packages:
                self.history_db.log_analysis_package(package)
            matrix = self._build_primary_matrix(cycle_id, packages)
        except Exception as exc:  # noqa: BLE001 - analyzer failure must not break the safe HOLD cycle.
            self._record(
                Event(
                    event_type=EventTypes.ANALYSIS_PASS_FAILED,
                    run_id=self.run_id,
                    cycle_id=cycle_id,
                    source="CycleRunner",
                    payload={
                        "stage": "RAW",
                        "symbol": self.config.symbol,
                        "timeframe": self.config.base_timeframe,
                        "analyzers": analyzer_names,
                        "error": str(exc),
                    },
                )
            )
            return {"status": "analysis_failed", "analyzers": analyzer_names, "error": str(exc)}

        summary = {
            "status": "analysis_ready",
            "analyzers": analyzer_names,
            "analysis_package_count": len(packages),
            "forecast_contribution_count": sum(len(package.forecast_contributions) for package in packages),
            "state_contribution_count": sum(len(package.state_contributions) for package in packages),
            "primary_matrix_id": matrix.matrix_id,
            "primary_zone_count": len(matrix.zones),
        }
        state_matrix = self._build_state_matrix(cycle_id, matrix, packages)
        summary["state_matrix_id"] = state_matrix.matrix_id
        summary["state_trust_score"] = state_matrix.trust_score
        summary["state_liquidity_state"] = state_matrix.liquidity_state
        summary["state_conflict_score"] = state_matrix.conflict_score
        scenario_result = self._build_scenario(cycle_id, matrix, state_matrix)
        summary["scenario_status"] = scenario_result.status
        summary["scenario_reason"] = scenario_result.reason
        summary["scenario_id"] = scenario_result.candidate.scenario_id if scenario_result.candidate else None
        summary["scenario_build_result"] = scenario_result
        event_summary = self._public_analysis_summary(summary)
        self._record(
            Event(
                event_type=EventTypes.ANALYSIS_PASS_COMPLETED,
                run_id=self.run_id,
                cycle_id=cycle_id,
                source="CycleRunner",
                payload={"stage": "RAW", "symbol": self.config.symbol, **event_summary},
            )
        )
        return summary

    def _build_primary_matrix(self, cycle_id: str, packages: List[AnalysisPackage]) -> ForecastMatrix:
        contributions = [
            contribution
            for package in packages
            for contribution in package.forecast_contributions
        ]
        matrix = ForecastMatrixEngine().build(cycle_id=cycle_id, symbol=self.config.symbol, contributions=contributions)
        self.history_db.log_forecast_matrix(matrix)
        self._record(
            Event(
                event_type=EventTypes.FORECAST_MATRIX_BUILT,
                run_id=self.run_id,
                cycle_id=cycle_id,
                source="CycleRunner",
                payload={
                    "matrix_id": matrix.matrix_id,
                    "symbol": matrix.symbol,
                    "matrix_layer": matrix.matrix_layer,
                    "primary_only": matrix.primary_only,
                    "zone_count": len(matrix.zones),
                    "contributor_count": len(matrix.contributor_ids),
                    "source_card_count": len(matrix.source_card_ids),
                    "not_trade_decision": True,
                },
            )
        )
        return matrix

    def _build_scenario(
        self,
        cycle_id: str,
        forecast_matrix: ForecastMatrix,
        state_matrix: StateMatrix,
    ) -> ScenarioBuildResult:
        result = ScenarioBuilder().build(
            cycle_id=cycle_id,
            forecast_matrix=forecast_matrix,
            state_matrix=state_matrix,
            market_snapshot=self.market_snapshot,
            profile_values=self.config.profile.values,
        )
        candidate = result.candidate
        self._record(
            Event(
                event_type=EventTypes.SCENARIO_BUILT,
                run_id=self.run_id,
                cycle_id=cycle_id,
                source="CycleRunner",
                payload={
                    "status": result.status,
                    "reason": result.reason,
                    "scenario_id": candidate.scenario_id if candidate else None,
                    "scenario_type": candidate.scenario_type if candidate else None,
                    "forecast_matrix_id": forecast_matrix.matrix_id,
                    "state_matrix_id": state_matrix.matrix_id,
                    "source_zone_ids": candidate.source_zone_ids if candidate else [],
                    "recheck_required": candidate.recheck_required if candidate else None,
                    "not_trade_decision": True,
                    **result.payload,
                },
            )
        )
        return result

    def _build_state_matrix(
        self,
        cycle_id: str,
        forecast_matrix: ForecastMatrix,
        packages: List[AnalysisPackage],
    ) -> StateMatrix:
        state_contributions = [
            contribution
            for package in packages
            for contribution in package.state_contributions
        ]
        matrix = StateMatrixEngine().build(
            cycle_id=cycle_id,
            symbol=self.config.symbol,
            market_snapshot=self.market_snapshot,
            forecast_matrix=forecast_matrix,
            state_contributions=state_contributions,
        )
        self.history_db.log_state_matrix(matrix)
        self._record(
            Event(
                event_type=EventTypes.STATE_MATRIX_BUILT,
                run_id=self.run_id,
                cycle_id=cycle_id,
                source="CycleRunner",
                payload={
                    "matrix_id": matrix.matrix_id,
                    "symbol": matrix.symbol,
                    "trust_score": matrix.trust_score,
                    "data_quality": matrix.data_quality,
                    "conflict_score": matrix.conflict_score,
                    "liquidity_state": matrix.liquidity_state,
                    "not_market_action": True,
                },
            )
        )
        return matrix

    def _calculate_trade_plan(self, cycle_id: str, analysis_summary: Dict[str, Any]) -> TradePlan:
        reason, dynamics_summary = self._hold_reason(analysis_summary)
        scenario_result = analysis_summary.get("scenario_build_result")
        if not isinstance(scenario_result, ScenarioBuildResult) or scenario_result.candidate is None:
            return TradePlan(
                decision="HOLD",
                symbol=self.config.symbol,
                reason=reason,
                profile_id=self.config.profile.profile_id,
                confidence=0.0,
                net_expected_edge_pct=0.0,
                dynamics_summary=dynamics_summary,
            )

        calculator = TradeCalculator(TradeCalculatorConfig.from_profile(self.config.profile.values))
        plan = calculator.calculate(
            candidate=scenario_result.candidate,
            market_snapshot=self.market_snapshot,
            profile_id=self.config.profile.profile_id,
        )
        return TradePlan(
            decision=plan.decision,
            symbol=plan.symbol,
            reason=plan.reason,
            profile_id=plan.profile_id,
            plan_role=plan.plan_role,
            source_type=plan.source_type,
            parent_plan_id=plan.parent_plan_id,
            blocked_by=plan.blocked_by,
            block_reason=plan.block_reason,
            forecast_matrix_id=plan.forecast_matrix_id,
            state_matrix_id=plan.state_matrix_id,
            entry_price=plan.entry_price,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
            rr_ratio=plan.rr_ratio,
            confidence=plan.confidence,
            net_expected_edge_pct=plan.net_expected_edge_pct,
            costs=plan.costs,
            dynamics_summary={
                **dynamics_summary,
                "scenario_build_status": scenario_result.status,
                "scenario_build_reason": scenario_result.reason,
                **plan.dynamics_summary,
            },
        )

    def _run_feedback_slice(self, cycle_id: str, plan: TradePlan, analysis_summary: Dict[str, Any]) -> None:
        state_matrix = self._state_matrix_from_summary(analysis_summary)
        risk_decision = RiskManager().evaluate(
            plan=plan,
            state_matrix=state_matrix,
            profile_values=self.config.profile.values,
            active_positions_count=0,
        )
        self._record(
            Event(
                event_type=EventTypes.RISK_DECISION_CREATED,
                run_id=self.run_id,
                cycle_id=cycle_id,
                source="RiskManager",
                payload=asdict(risk_decision),
            )
        )

        attempt = ExchangeExecutor(self.config).execute(plan, risk_decision)
        if attempt.request is not None:
            self._record(
                Event(
                    event_type=EventTypes.EXECUTOR_REQUEST_CREATED,
                    run_id=self.run_id,
                    cycle_id=cycle_id,
                    source="ExchangeExecutor",
                    payload=asdict(attempt.request),
                )
            )
        self._record(
            Event(
                event_type=EventTypes.EXECUTOR_RESULT_RECORDED,
                run_id=self.run_id,
                cycle_id=cycle_id,
                source="ExchangeExecutor",
                payload=asdict(attempt.result),
            )
        )

        shadow_request = ShadowEngine().on_trade_plan(plan, risk_decision)
        self._record(
            Event(
                event_type=EventTypes.SHADOW_SCENARIO_CREATED,
                run_id=self.run_id,
                cycle_id=cycle_id,
                source="ShadowEngine",
                payload=asdict(shadow_request),
            )
        )

        if risk_decision.warnings or attempt.result.status != "ACCEPTED":
            lab_request = ExperimentDispatcher().dispatch(
                {
                    "trade_plan": plan,
                    "source_id": attempt.result.result_id,
                    "purpose": "risk_or_execution_warning_check",
                }
            )
            self._record(
                Event(
                    event_type=EventTypes.LAB_EXPERIMENT_CREATED,
                    run_id=self.run_id,
                    cycle_id=cycle_id,
                    source="ExperimentDispatcher",
                    payload=asdict(lab_request),
                )
            )

        scenario_id = plan.dynamics_summary.get("scenario_id")
        evidence = EvidenceCollector().collect_real_testnet(
            profile_id=self.config.profile.profile_id,
            parameter_snapshot=self.config.profile.values,
            plan_id=plan.plan_id,
            scenario_id=str(scenario_id) if scenario_id else None,
            risk_decision_id=risk_decision.risk_decision_id,
            executor_result_id=attempt.result.result_id,
            observations={
                "risk_status": risk_decision.status,
                "risk_warnings": risk_decision.warnings,
                "executor_status": attempt.result.status,
                "executor_reason": attempt.result.reason,
                "plan_decision": plan.decision,
                "net_expected_edge_pct": plan.net_expected_edge_pct,
                "rr_ratio": plan.rr_ratio,
            },
        )
        self._record(
            Event(
                event_type=EventTypes.AUTOTUNE_EVIDENCE_RECORDED,
                run_id=self.run_id,
                cycle_id=cycle_id,
                source="EvidenceCollector",
                payload=asdict(evidence),
            )
        )

    def _state_matrix_from_summary(self, analysis_summary: Dict[str, Any]) -> StateMatrix | None:
        scenario_result = analysis_summary.get("scenario_build_result")
        if not isinstance(scenario_result, ScenarioBuildResult) or scenario_result.candidate is None:
            return None
        return StateMatrix(
            symbol=self.config.symbol,
            cycle_id=scenario_result.candidate.cycle_id,
            trust_score=scenario_result.candidate.trust_score,
            volatility_state="from_runtime_summary",
            conflict_score=float(analysis_summary.get("state_conflict_score", 0.0)),
            data_quality=self.market_snapshot.quality.score if self.market_snapshot else 0.0,
            liquidity_state=analysis_summary.get("state_liquidity_state"),
            matrix_id=scenario_result.candidate.state_matrix_id,
            payload={"reconstructed_for_risk_gate": True},
        )

    def _hold_reason(self, analysis_summary: Dict[str, Any]) -> tuple[str, dict[str, object]]:
        if self.market_snapshot is None:
            reason = "Data warmup failed; analyzers and matrix were not started"
            summary: dict[str, object] = {"status": "data_warmup_failed"}
            if self.warmup_error:
                summary["warmup_error"] = self.warmup_error
            return reason, summary

        candle_counts = {
            timeframe: series.count for timeframe, series in sorted(self.market_snapshot.candles.items())
        }
        if not self.market_snapshot.quality.is_usable:
            return (
                "Market snapshot created but quality is not usable; analyzers and matrix were not started",
                {
                    "status": "market_snapshot_not_usable",
                    "snapshot_id": self.market_snapshot.snapshot_id,
                    "quality_score": self.market_snapshot.quality.score,
                    "quality_usable": self.market_snapshot.quality.is_usable,
                    "issue_codes": self.market_snapshot.quality.issue_codes,
                    "candle_counts": candle_counts,
                },
            )

        scenario_result = analysis_summary.get("scenario_build_result")
        if isinstance(scenario_result, ScenarioBuildResult) and scenario_result.candidate is None:
            return (
                f"Market snapshot analyzed; no computable scenario: {scenario_result.reason}",
                {
                    "status": "no_computable_scenario",
                    "snapshot_id": self.market_snapshot.snapshot_id,
                    "quality_score": self.market_snapshot.quality.score,
                    "quality_usable": self.market_snapshot.quality.is_usable,
                    "candle_counts": candle_counts,
                    "analysis_summary": self._public_analysis_summary(analysis_summary),
                },
            )

        return (
            "Market snapshot analyzed; scenario calculated into TradePlan for RiskManager review",
            {
                "status": "trade_plan_calculated_for_risk_review",
                "snapshot_id": self.market_snapshot.snapshot_id,
                "quality_score": self.market_snapshot.quality.score,
                "quality_usable": self.market_snapshot.quality.is_usable,
                "candle_counts": candle_counts,
                "analysis_summary": self._public_analysis_summary(analysis_summary),
            },
        )

    @staticmethod
    def _public_analysis_summary(analysis_summary: Dict[str, Any]) -> Dict[str, Any]:
        return {key: value for key, value in analysis_summary.items() if key != "scenario_build_result"}

    def _record(self, event: Event) -> None:
        self.event_log.append(event)
        self.history_db.log_event(event)
