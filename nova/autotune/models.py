"""Autotuner recommendation contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from nova.core.ids import RECOMMENDATION, new_id


@dataclass(frozen=True)
class AutotuneRecommendation:
    target_profile_id: str
    parameter_changes: Dict[str, object]
    evidence_ids: List[str]
    sample_size: int
    confidence: float
    reason: str
    rollback_condition: Optional[str] = None
    recommendation_id: str = field(default_factory=lambda: new_id(RECOMMENDATION))

