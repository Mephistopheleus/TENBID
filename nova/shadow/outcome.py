"""Outcome contracts for real, shadow and lab scenarios."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

from nova.core.ids import OUTCOME, new_id


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ScenarioOutcome:
    scenario_id: str
    source_type: str
    result: str
    gross_pnl_pct: float
    net_pnl_pct: float
    mfe_pct: float
    mae_pct: float
    duration_sec: int
    resolution_method: str
    quality: float
    planned_costs: Dict[str, float] = field(default_factory=dict)
    actual_costs: Dict[str, float] = field(default_factory=dict)
    payload: Dict[str, object] = field(default_factory=dict)
    outcome_id: str = field(default_factory=lambda: new_id(OUTCOME))
    created_at: str = field(default_factory=utc_now)
    notes: Optional[str] = None


class OutcomeResult:
    PENDING = "PENDING"
    UNRESOLVED = "UNRESOLVED"
    EXECUTOR_ACCEPTED = "EXECUTOR_ACCEPTED"
    EXECUTOR_REJECTED = "EXECUTOR_REJECTED"
    EXECUTOR_NOT_CALLED = "EXECUTOR_NOT_CALLED"
    OBSERVED_WIN = "OBSERVED_WIN"
    OBSERVED_LOSS = "OBSERVED_LOSS"
    OBSERVED_FLAT = "OBSERVED_FLAT"


class ResolutionMethod:
    PENDING = "PENDING"
    EXECUTION_ACK = "EXECUTION_ACK"
    TESTNET_CLOSE = "TESTNET_CLOSE"
    NOT_EXECUTED = "NOT_EXECUTED"
    OHLC_CLEAR = "OHLC_CLEAR"
    ONE_MINUTE_REPLAY = "ONE_MINUTE_REPLAY"
    AGGTRADES_REPLAY = "AGGTRADES_REPLAY"
    AMBIGUOUS = "AMBIGUOUS"
