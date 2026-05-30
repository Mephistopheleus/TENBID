"""Cycle runner.

The first cycle implementation creates a traceable HOLD TradePlan without
market data. This proves config, IDs, EventLog and HistoryDB before Binance or
analyzers are connected.
"""

from __future__ import annotations

from nova.core.config_loader import RuntimeConfig
from nova.core.event_log import EventLog
from nova.core.events import Event, EventTypes
from nova.core.history_db import HistoryDB
from nova.core.ids import CYCLE, new_id
from nova.decision.trade_plan import TradePlan


class CycleRunner:
    def __init__(
        self,
        run_id: str,
        config: RuntimeConfig,
        event_log: EventLog,
        history_db: HistoryDB,
    ) -> None:
        self.run_id = run_id
        self.config = config
        self.event_log = event_log
        self.history_db = history_db

    def run_once(self) -> TradePlan:
        cycle_id = new_id(CYCLE)
        self._record(
            Event(
                event_type=EventTypes.CYCLE_STARTED,
                run_id=self.run_id,
                cycle_id=cycle_id,
                source="CycleRunner",
                payload={"symbol": self.config.symbol, "profile_id": self.config.profile.profile_id},
            )
        )

        plan = TradePlan(
            decision="HOLD",
            symbol=self.config.symbol,
            reason="Runtime foundation cycle: no market snapshot or forecast contributions yet",
            profile_id=self.config.profile.profile_id,
            confidence=0.0,
            net_expected_edge_pct=0.0,
            dynamics_summary={"status": "not_available_yet"},
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

    def _record(self, event: Event) -> None:
        self.event_log.append(event)
        self.history_db.log_event(event)
