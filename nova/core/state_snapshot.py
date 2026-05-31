"""Immutable runtime state snapshots for learning context.

StateSnapshot is logged at cycle boundaries so Shadow and Autotuner can learn
which conditions existed at decision time. It is context, not a training label
and not a trade decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from nova.core.ids import STATE_SNAPSHOT, new_id


class StateSnapshotStage:
    PRE_ANALYSIS = "PRE_ANALYSIS"
    POST_MATRIX = "POST_MATRIX"
    PRE_DECISION = "PRE_DECISION"
    POST_DECISION = "POST_DECISION"
    OUTCOME_CONTEXT = "OUTCOME_CONTEXT"


@dataclass(frozen=True)
class StateSnapshot:
    symbol: str
    run_id: str
    cycle_id: str
    stage: str
    market_snapshot_id: Optional[str]
    data_quality: float
    data_usable: bool
    training_role: str = "CONTEXT_NOT_LABEL"
    volatility_state: str = "unknown"
    liquidity_state: Optional[str] = None
    scale_state: str = "not_evaluated"
    conflict_score: float = 0.0
    source_matrix_ids: List[str] = field(default_factory=list)
    source_card_ids: List[str] = field(default_factory=list)
    source_event_ids: List[str] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    state_snapshot_id: str = field(default_factory=lambda: new_id(STATE_SNAPSHOT))
