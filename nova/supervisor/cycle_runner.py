"""Cycle runner.

The runtime cycle now accepts the current MarketSnapshot from the data warmup
stage, but still returns a traceable HOLD until analyzers and Matrix Core are
connected.
"""

from __future__ import annotations

from nova.core.config_loader import RuntimeConfig
from nova.core.event_log import EventLog
from nova.core.events import Event, EventTypes
from nova.core.history_db import HistoryDB
from nova.core.ids import CYCLE, new_id
from nova.core.state_snapshot import StateSnapshot, StateSnapshotStage
from nova.data.models import MarketSnapshot
from nova.decision.trade_plan import TradePlan


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

        reason, dynamics_summary = self._hold_reason()
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

    def _hold_reason(self) -> tuple[str, dict[str, object]]:
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
            "Market snapshot ready; analyzers and matrix are not connected yet",
            {
                "status": "market_snapshot_ready",
                "snapshot_id": self.market_snapshot.snapshot_id,
                "quality_score": self.market_snapshot.quality.score,
                "quality_usable": self.market_snapshot.quality.is_usable,
                "candle_counts": candle_counts,
            },
        )

    def _record(self, event: Event) -> None:
        self.event_log.append(event)
        self.history_db.log_event(event)
