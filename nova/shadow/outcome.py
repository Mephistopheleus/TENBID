"""Outcome contracts for real, shadow and lab scenarios."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from nova.core.ids import OUTCOME, new_id


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
    outcome_id: str = field(default_factory=lambda: new_id(OUTCOME))
    notes: Optional[str] = None


class ResolutionMethod:
    OHLC_CLEAR = "OHLC_CLEAR"
    ONE_MINUTE_REPLAY = "ONE_MINUTE_REPLAY"
    AGGTRADES_REPLAY = "AGGTRADES_REPLAY"
    AMBIGUOUS = "AMBIGUOUS"

