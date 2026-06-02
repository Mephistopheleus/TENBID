"""Build MarketEpisode objects from persisted runtime memory."""

from __future__ import annotations

import json
from typing import Any

from nova.core.history_db import HistoryDB
from nova.episodes.models import MarketEpisode


class EpisodeBuilder:
    def __init__(self, history_db: HistoryDB) -> None:
        self.history_db = history_db

    def build_for_plan(self, plan_id: str) -> MarketEpisode | None:
        with self.history_db._connect() as conn:  # noqa: SLF001 - read-only episode assembly from NOVA memory.
            plan_row = conn.execute(
                "SELECT run_id, cycle_id, symbol, timestamp, payload_json FROM trade_plans WHERE plan_id = ?",
                (plan_id,),
            ).fetchone()
            if plan_row is None:
                return None
            run_id = plan_row["run_id"]
            cycle_id = plan_row["cycle_id"]
            events = conn.execute(
                "SELECT event_id, timestamp, event_type, payload_json FROM events WHERE run_id = ? AND cycle_id = ? ORDER BY timestamp",
                (run_id, cycle_id),
            ).fetchall()
            outcomes = conn.execute(
                "SELECT outcome_id, created_at, result, resolution_method, net_pnl_pct, payload_json FROM scenario_outcomes "
                "WHERE json_extract(payload_json, '$.plan_id') = ? ORDER BY created_at",
                (plan_id,),
            ).fetchall()

        timestamps = [str(row["timestamp"]) for row in events]
        outcome_times = [str(row["created_at"]) for row in outcomes if row["created_at"]]
        start_time = min(timestamps or [str(plan_row["timestamp"])])
        end_time = max(timestamps + outcome_times or [str(plan_row["timestamp"])])
        return MarketEpisode(
            symbol=str(plan_row["symbol"]),
            start_time=start_time,
            end_time=end_time,
            related_plan_id=plan_id,
            event_ids=[str(row["event_id"]) for row in events],
            payload={
                "run_id": run_id,
                "cycle_id": cycle_id,
                "plan": self._json(plan_row["payload_json"]),
                "events": [
                    {"event_id": row["event_id"], "timestamp": row["timestamp"], "event_type": row["event_type"], "payload": self._json(row["payload_json"])}
                    for row in events
                ],
                "outcomes": [
                    {
                        "outcome_id": row["outcome_id"],
                        "created_at": row["created_at"],
                        "result": row["result"],
                        "resolution_method": row["resolution_method"],
                        "net_pnl_pct": row["net_pnl_pct"],
                        "payload": self._json(row["payload_json"]),
                    }
                    for row in outcomes
                ],
            },
        )

    @staticmethod
    def _json(raw: str | None) -> dict[str, Any]:
        if not raw:
            return {}
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {"value": payload}
