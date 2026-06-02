"""Cycle runner.

CycleRunner stitches data snapshot, state snapshot, analyzers and matrix into a
traceable context package. It is not the market-action calculator; until that
separate layer exists, the runtime finishes with a safe placeholder TradePlan.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List

from nova.analyzers.btc_correlation import BTCCorrelationAnalyzer
from nova.analyzers.contracts import AnalysisPackage
from nova.analyzers.derivatives_context import DerivativesContextAnalyzer
from nova.analyzers.fractal_structure import FractalStructureAnalyzer
from nova.analyzers.market_structure import MarketStructureAnalyzer
from nova.analyzers.news_context import NewsContextAnalyzer
from nova.analyzers.orderbook_liquidity import OrderbookLiquidityAnalyzer
from nova.analyzers.pattern_formation import PatternFormationAnalyzer
from nova.analyzers.registry import AnalyzerRegistry
from nova.analyzers.runner import AnalyzerRunner
from nova.analyzers.volatility_regime import VolatilityRegimeAnalyzer
from nova.analyzers.volume_profile import VolumeProfileAnalyzer
from nova.autotune.evidence_collector import EvidenceCollector
from nova.autotune.models import AutotuneEvidenceSource
from nova.autotune.profile_manager import ProfileManager
from nova.autotune.trust_engine import TrustEngine
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
from nova.execution.order_tracker import OrderTracker
from nova.execution.position_manager import PositionManager
from nova.labs.experiment_dispatcher import ExperimentDispatcher
from nova.matrix.forecast_matrix import ForecastMatrixEngine
from nova.matrix.models import ForecastMatrix, StateMatrix
from nova.matrix.state_matrix import StateMatrixEngine
from nova.reports.reporter import Reporter
from nova.risk.risk_manager import RiskManager
from nova.risk.models import RiskDecision
from nova.scenario.builder import ScenarioBuilder
from nova.scenario.models import ScenarioBuildResult
from nova.shadow.shadow_engine import ShadowEngine
from nova.shadow.outcome_recorder import OutcomeRecorder
from nova.shadow.outcome_resolver import ScenarioOutcomeResolver


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
            self._resolve_pending_outcomes(cycle_id)
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
        registry = AnalyzerRegistry(
            [
                MarketStructureAnalyzer(),
                VolumeProfileAnalyzer(),
                OrderbookLiquidityAnalyzer(),
                VolatilityRegimeAnalyzer(),
                FractalStructureAnalyzer(),
                PatternFormationAnalyzer(),
                BTCCorrelationAnalyzer(),
                DerivativesContextAnalyzer(),
                NewsContextAnalyzer(),
            ]
        )
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
        profile_values = self._profile_values_with_outcome_count()
        pre_risk_position = None
        active_positions_count = 0
        position_manager = None
        if bool(profile_values.get("position_manager_enabled", True)):
            position_manager = PositionManager(self.config, history_db=self.history_db)
            for management in position_manager.manage_open_records(
                risk_decision=self._position_management_risk_decision(plan, state_matrix, profile_values)
            ):
                self._record_position_management(cycle_id, management)
            try:
                pre_risk_position = position_manager.current_position(plan.symbol)
                active_positions_count = 1 if pre_risk_position is not None else 0
                self._record(
                    Event(
                        event_type=EventTypes.POSITION_MANAGER_RECORDED,
                        run_id=self.run_id,
                        cycle_id=cycle_id,
                        source="PositionManager",
                        payload={
                            "status": "PRE_RISK_POSITION_CHECK",
                            "active_positions_count": active_positions_count,
                            "position": PositionManager._position_payload(plan, pre_risk_position)
                            if pre_risk_position is not None
                            else None,
                        },
                    )
                )
            except Exception as exc:  # noqa: BLE001 - position visibility failure must stop execution, not the cycle.
                active_positions_count = int(profile_values.get("max_concurrent_positions", 1))
                self._record(
                    Event(
                        event_type=EventTypes.POSITION_MANAGER_RECORDED,
                        run_id=self.run_id,
                        cycle_id=cycle_id,
                        source="PositionManager",
                        payload={
                            "status": "PRE_RISK_POSITION_CHECK_FAILED",
                            "error": str(exc),
                            "active_positions_count_assumed": active_positions_count,
                        },
                    )
                )
        risk_decision = RiskManager().evaluate(
            plan=plan,
            state_matrix=state_matrix,
            profile_values=profile_values,
            active_positions_count=active_positions_count,
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

        executor = ExchangeExecutor(self.config)
        attempt = executor.execute(plan, risk_decision)
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

        executor_accepted = attempt.result.status == "ACCEPTED"
        close_attempt = None
        position_management = None
        if executor_accepted:
            order_reconciliation = OrderTracker(executor.connector()).reconcile_attempt(attempt)
            self._record(
                Event(
                    event_type=EventTypes.ORDER_STATUS_RECONCILED
                    if order_reconciliation.status == "RECONCILED"
                    else EventTypes.ORDER_STATUS_RECONCILIATION_FAILED,
                    run_id=self.run_id,
                    cycle_id=cycle_id,
                    source="OrderTracker",
                    payload=asdict(order_reconciliation),
                )
            )
            position_manager = position_manager or PositionManager(self.config, history_db=self.history_db)
            position_management = position_manager.manage_after_entry(
                plan=plan,
                entry_attempt=attempt,
                risk_decision=risk_decision,
            )
            if position_management.position is not None:
                position_management = self._with_registered_position(
                    manager=position_manager,
                    plan=plan,
                    attempt=attempt,
                    position_management=position_management,
                )
            close_attempt = position_management.close_attempt
            self._record(
                Event(
                    event_type=EventTypes.POSITION_MANAGER_RECORDED,
                    run_id=self.run_id,
                    cycle_id=cycle_id,
                    source="PositionManager",
                    payload={
                        "status": position_management.status,
                        "reason": position_management.reason,
                        "position": position_management.payload,
                        "close_attempt_result_id": close_attempt.result.result_id if close_attempt else None,
                    },
                )
            )
            if close_attempt is not None:
                if close_attempt.request is not None:
                    self._record(
                        Event(
                            event_type=EventTypes.EXECUTOR_REQUEST_CREATED,
                            run_id=self.run_id,
                            cycle_id=cycle_id,
                            source="PositionManager",
                            payload=asdict(close_attempt.request),
                        )
                    )
                self._record(
                    Event(
                        event_type=EventTypes.EXECUTOR_RESULT_RECORDED,
                        run_id=self.run_id,
                        cycle_id=cycle_id,
                        source="PositionManager",
                        payload={**asdict(close_attempt.result), "position_manager_close": True},
                    )
                )

        if executor_accepted and bool(profile_values.get("testnet_auto_close_enabled", False)):
            close_attempt = executor.close_reduce_only(
                trade_plan=plan,
                entry_attempt=attempt,
                risk_decision=risk_decision,
            )
            if close_attempt.request is not None:
                self._record(
                    Event(
                        event_type=EventTypes.EXECUTOR_REQUEST_CREATED,
                        run_id=self.run_id,
                        cycle_id=cycle_id,
                        source="ExchangeExecutor",
                        payload=asdict(close_attempt.request),
                    )
                )
            self._record(
                Event(
                    event_type=EventTypes.EXECUTOR_RESULT_RECORDED,
                    run_id=self.run_id,
                    cycle_id=cycle_id,
                    source="ExchangeExecutor",
                    payload={**asdict(close_attempt.result), "close_attempt": True},
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

        lab_request = None
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

        plan_scenario_id = plan.dynamics_summary.get("scenario_id")
        evidence_scenario_id = str(plan_scenario_id) if executor_accepted and plan_scenario_id else shadow_request.scenario_id
        evidence = EvidenceCollector().collect_feedback(
            source_type=AutotuneEvidenceSource.REAL_EXCHANGE if executor_accepted else AutotuneEvidenceSource.SHADOW,
            source_weight=1.0 if executor_accepted else 0.0,
            profile_id=self.config.profile.profile_id,
            parameter_snapshot=profile_values,
            plan_id=plan.plan_id,
            scenario_id=evidence_scenario_id,
            risk_decision_id=risk_decision.risk_decision_id,
            executor_result_id=attempt.result.result_id,
            observations={
                "risk_status": risk_decision.status,
                "risk_warnings": risk_decision.warnings,
                "risk_hard_blocks": risk_decision.hard_blocks,
                "executor_status": attempt.result.status,
                "executor_reason": attempt.result.reason,
                "plan_decision": plan.decision,
                "analyzer_probability": plan.dynamics_summary.get("analyzer_probability"),
                "autotuner_trust_points": plan.dynamics_summary.get("autotuner_trust_points"),
                "effective_confidence": plan.dynamics_summary.get("effective_confidence", plan.confidence),
                "shadow_outcome_sample_count": profile_values.get("shadow_outcome_sample_count", 0),
                "minimum_shadow_samples_before_execution": profile_values.get("minimum_shadow_samples_before_execution", 50),
                "net_expected_edge_pct": plan.net_expected_edge_pct,
                "rr_ratio": plan.rr_ratio,
                "recheck_required": plan.dynamics_summary.get("recheck_required"),
                "state_liquidity_state": state_matrix.liquidity_state if state_matrix else None,
                "calculator_flags": plan.dynamics_summary.get("calculator_flags"),
                "position_management_status": position_management.status if position_management else None,
                "position_management_reason": position_management.reason if position_management else None,
            },
        )
        self.history_db.log_autotune_evidence(evidence)
        self._record(
            Event(
                event_type=EventTypes.AUTOTUNE_EVIDENCE_RECORDED,
                run_id=self.run_id,
                cycle_id=cycle_id,
                source="EvidenceCollector",
                payload=asdict(evidence),
            )
        )

        outcome_recorder = OutcomeRecorder(self.history_db)
        if executor_accepted:
            _, outcome_event = outcome_recorder.record_execution_ack(
                run_id=self.run_id,
                cycle_id=cycle_id,
                scenario_id=evidence_scenario_id,
                plan=plan,
                risk_decision=risk_decision,
                attempt=attempt,
                evidence=evidence,
            )
            if close_attempt is not None:
                if position_management is not None and position_management.close_attempt is close_attempt:
                    _, close_outcome_event = outcome_recorder.record_position_manager_close(
                        run_id=self.run_id,
                        cycle_id=cycle_id,
                        scenario_id=evidence_scenario_id,
                        plan=plan,
                        entry_attempt=attempt,
                        close_attempt=close_attempt,
                        risk_decision=risk_decision,
                        evidence=evidence,
                        close_reason=position_management.reason,
                        position_payload=position_management.payload,
                    )
                else:
                    _, close_outcome_event = outcome_recorder.record_exchange_close(
                        run_id=self.run_id,
                        cycle_id=cycle_id,
                        scenario_id=evidence_scenario_id,
                        plan=plan,
                        entry_attempt=attempt,
                        close_attempt=close_attempt,
                        risk_decision=risk_decision,
                        evidence=evidence,
                    )
        else:
            _, outcome_event = outcome_recorder.record_shadow_placeholder(
                run_id=self.run_id,
                cycle_id=cycle_id,
                request=shadow_request,
                plan=plan,
                risk_decision=risk_decision,
                evidence=evidence,
            )
        self._record(outcome_event)
        if executor_accepted and close_attempt is not None:
            self._record(close_outcome_event)

        execution_report = Reporter().generate_execution_report(
            plan=plan,
            risk_decision=risk_decision,
            attempt=attempt,
            close_attempt=close_attempt,
            shadow_request=shadow_request,
            lab_request=lab_request,
            autotune_evidence=evidence,
        )
        self._record(
            Event(
                event_type=EventTypes.TRADE_EXECUTION_REPORT_CREATED,
                run_id=self.run_id,
                cycle_id=cycle_id,
                source="Reporter",
                payload=execution_report,
            )
        )

    def _profile_values_with_outcome_count(self) -> Dict[str, Any]:
        values = dict(self.config.profile.values)
        values["shadow_outcome_sample_count"] = self.history_db.count_traceable_outcomes()
        return values

    def _record_position_management(self, cycle_id: str, management: object) -> None:
        close_attempt = getattr(management, "close_attempt", None)
        self._record(
            Event(
                event_type=EventTypes.POSITION_MANAGER_RECORDED,
                run_id=self.run_id,
                cycle_id=cycle_id,
                source="PositionManager",
                payload={
                    "status": getattr(management, "status", None),
                    "reason": getattr(management, "reason", None),
                    "position": getattr(management, "payload", None),
                    "close_attempt_result_id": close_attempt.result.result_id if close_attempt else None,
                },
            )
        )
        if close_attempt is None:
            return
        if close_attempt.request is not None:
            self._record(
                Event(
                    event_type=EventTypes.EXECUTOR_REQUEST_CREATED,
                    run_id=self.run_id,
                    cycle_id=cycle_id,
                    source="PositionManager",
                    payload=asdict(close_attempt.request),
                )
            )
        self._record(
            Event(
                event_type=EventTypes.EXECUTOR_RESULT_RECORDED,
                run_id=self.run_id,
                cycle_id=cycle_id,
                source="PositionManager",
                payload={**asdict(close_attempt.result), "position_manager_close": True},
            )
        )

    def _position_management_risk_decision(
        self,
        plan: TradePlan,
        state_matrix: StateMatrix | None,
        profile_values: Dict[str, Any],
    ) -> RiskDecision:
        return RiskDecision(
            plan_id=plan.plan_id,
            status="POSITION_MANAGEMENT",
            reason="manage_existing_position",
            approved_for_executor=True,
            profile_id=self.config.profile.profile_id,
            state_matrix_id=state_matrix.matrix_id if state_matrix else None,
            payload={
                "not_new_entry": True,
                "profile_id": self.config.profile.profile_id,
                "shadow_outcome_sample_count": profile_values.get("shadow_outcome_sample_count"),
            },
        )

    @staticmethod
    def _with_registered_position(
        *,
        manager: PositionManager,
        plan: TradePlan,
        attempt: object,
        position_management: object,
    ) -> object:
        if getattr(position_management, "status", None) != "OPEN":
            return position_management
        position = getattr(position_management, "position", None)
        if position is None:
            return position_management
        registered = manager.register_open_position(plan=plan, position=position, entry_attempt=attempt)
        position_management.payload.update({"active_position_record": registered})
        return position_management

    def _resolve_pending_outcomes(self, cycle_id: str) -> None:
        resolver = ScenarioOutcomeResolver()
        resolved_count = 0
        for pending in self.history_db.pending_outcomes(limit=50):
            resolution = resolver.resolve_pending(pending, self.market_snapshot)
            if not resolution.resolved or resolution.outcome is None:
                continue
            self.history_db.log_scenario_outcome(resolution.outcome)
            resolved_count += 1
            self._record(
                Event(
                    event_type=EventTypes.SCENARIO_OUTCOME_RECORDED,
                    run_id=self.run_id,
                    cycle_id=cycle_id,
                    source="ScenarioOutcomeResolver",
                    payload={
                        **asdict(resolution.outcome),
                        "resolved_from_outcome_id": resolution.original_outcome_id,
                        "resolution_reason": resolution.reason,
                        "traceable_outcome_sample_count": self.history_db.count_traceable_outcomes(),
                    },
                )
            )
        self._build_trust_recommendation(cycle_id, resolved_count)

    def _build_trust_recommendation(self, cycle_id: str, newly_resolved_count: int) -> None:
        outcomes = self.history_db.traceable_outcomes(limit=500)
        result = TrustEngine().build_recommendation(
            target_profile_id=self.config.profile.profile_id,
            profile_values=self._profile_values_with_outcome_count(),
            outcomes=outcomes,
            evidence_ids=[],
        )
        if result.recommendation is None:
            if newly_resolved_count > 0:
                self._record(
                    Event(
                        event_type=EventTypes.AUTOTUNE_RECOMMENDATION_CREATED,
                        run_id=self.run_id,
                        cycle_id=cycle_id,
                        source="TrustEngine",
                        payload={
                            "status": "no_recommendation",
                            "reason": result.reason,
                            "sample_count": result.sample_count,
                            "newly_resolved_count": newly_resolved_count,
                            "proposed_trust_points": result.proposed_trust_points,
                            "diagnostics": result.diagnostics or {},
                        },
                    )
                )
            return
        self.history_db.log_autotune_recommendation(result.recommendation)
        apply_result = ProfileManager(self.config.root_dir / "config" / "active_profile.json").apply_recommendation(
            result.recommendation
        )
        self._record(
            Event(
                event_type=EventTypes.AUTOTUNE_RECOMMENDATION_CREATED,
                run_id=self.run_id,
                cycle_id=cycle_id,
                source="TrustEngine",
                payload={
                    "status": "recommendation_applied"
                    if apply_result.status == "applied"
                    else "recommendation_partially_applied"
                    if apply_result.status == "partially_applied"
                    else "recommendation_rejected_by_policy",
                    "recommendation": asdict(result.recommendation),
                    "profile_apply_result": asdict(apply_result),
                    "sample_count": result.sample_count,
                    "wins": result.win_count,
                    "losses": result.loss_count,
                    "flats": result.flat_count,
                    "proposed_trust_points": result.proposed_trust_points,
                    "newly_resolved_count": newly_resolved_count,
                    "diagnostics": result.diagnostics or {},
                },
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
