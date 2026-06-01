"""Scenario contracts.

A ScenarioCandidate is a bounded calculation hypothesis built from Matrix and
State context. It is not a market command and not executor input by itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from nova.core.ids import SCENARIO, new_id


class ScenarioStatus:
    CANDIDATE = "CANDIDATE"
    NO_SCENARIO = "NO_SCENARIO"
    RECHECK_REQUIRED = "RECHECK_REQUIRED"


@dataclass(frozen=True)
class ScenarioCandidate:
    symbol: str
    cycle_id: str
    scenario_type: str
    price_low: float
    price_high: float
    reference_price: float
    horizon_min: int
    probability: float
    confidence: float
    trust_score: float
    forecast_matrix_id: str
    state_matrix_id: str
    source_zone_ids: List[str]
    invalidation_price: Optional[float] = None
    recheck_required: bool = False
    reason: str = "computable_scenario"
    payload: Dict[str, object] = field(default_factory=dict)
    scenario_id: str = field(default_factory=lambda: new_id(SCENARIO))


@dataclass(frozen=True)
class ScenarioBuildResult:
    status: str
    reason: str
    candidate: Optional[ScenarioCandidate] = None
    payload: Dict[str, object] = field(default_factory=dict)

