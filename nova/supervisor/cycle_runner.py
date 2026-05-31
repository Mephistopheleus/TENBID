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
