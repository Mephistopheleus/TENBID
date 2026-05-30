"""SQLite history database for the first runnable NOVA runtime.

JSONL EventLog is the append-only journal; SQLite provides queryable memory.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

from nova.core.events import Event
from nova.decision.trade_plan import TradePlan


class HistoryDB:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    run_id TEXT,
                    cycle_id TEXT,
                    source TEXT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_plans (
                    plan_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    run_id TEXT,
                    cycle_id TEXT,
                    decision TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def log_event(self, event: Event) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO events (
                    event_id, timestamp, run_id, cycle_id, source, event_type, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.timestamp,
                    event.run_id,
                    event.cycle_id,
                    event.source,
                    event.event_type,
                    json.dumps(event.payload, ensure_ascii=False, default=str),
                ),
            )

    def log_trade_plan(self, plan: TradePlan, run_id: str, cycle_id: str) -> None:
        payload: Dict[str, Any] = asdict(plan)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO trade_plans (
                    plan_id, run_id, cycle_id, decision, symbol, reason, profile_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.plan_id,
                    run_id,
                    cycle_id,
                    plan.decision,
                    plan.symbol,
                    plan.reason,
                    plan.profile_id,
                    json.dumps(payload, ensure_ascii=False, default=str),
                ),
            )

