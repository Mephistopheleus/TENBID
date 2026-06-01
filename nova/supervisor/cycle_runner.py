"""Cycle runner.

CycleRunner stitches data snapshot, state snapshot, analyzers and matrix into a
traceable context package. It is not the market-action calculator; until that
separate layer exists, the runtime finishes with a safe placeholder TradePlan.
"""

from __future__ import annotations

from typing import Any, Dict, List

from nova.analyzers.contracts import AnalysisPackage
from nova.analyzers.market_structure import MarketStructureAnalyzer
from nova.analyzers.registry import AnalyzerRegistry
from nova.analyzers.runner import AnalyzerRunner
from nova.core.config_loader import RuntimeConfig
from nova.core.event_log import EventLog
from nova.core.events import Event, EventTypes
from nova.core.history_db import HistoryDB
from nova.core.ids import CYCLE, new_id
from nova.core.state_snapshot import StateSnapshot, StateSnapshotStage
from nova.data.models import MarketSnapshot
from nova.decision.trade_plan import TradePlan
from nova.matrix.forecast_matrix import ForecastMatrixEngine
from nova.matrix.models import ForecastMatrix, StateMatrix
from nova.matrix.state_matrix import StateMatrixEngine


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

        reason, dynamics_summary = self._hold_reason(analysis_summary)
        plan = TradePlan(
            decision="HOLD",
            symbol=self.config.symbol,
            reason=reason,
            profile_id=self.config.profile.profile_id,
            confidence=0.0,
            net_expected_edge_pct=0.0,
            dynamics_summary=dynamics_summary,
        )
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
                },
            )
        )
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
        self._record(
            Event(
                event_type=EventTypes.ANALYSIS_PASS_COMPLETED,
                run_id=self.run_id,
                cycle_id=cycle_id,
                source="CycleRunner",
                payload={"stage": "RAW", "symbol": self.config.symbol, **summary},
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

        return (
            "Market snapshot analyzed; matrix context ready; trade decision path is not connected yet",
            {
                "status": "analysis_and_matrix_ready",
                "snapshot_id": self.market_snapshot.snapshot_id,
                "quality_score": self.market_snapshot.quality.score,
                "quality_usable": self.market_snapshot.quality.is_usable,
                "candle_counts": candle_counts,
                "analysis_summary": analysis_summary,
            },
        )

    def _record(self, event: Event) -> None:
        self.event_log.append(event)
        self.history_db.log_event(event)
