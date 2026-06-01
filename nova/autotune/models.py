"""Autotuner evidence and recommendation contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from nova.core.ids import RECOMMENDATION, new_id


class AutotuneEvidenceSource:
    REAL_TESTNET = "REAL_TESTNET"
    SHADOW = "SHADOW"
    LAB = "LAB"


@dataclass(frozen=True)
class AutotuneEvidence:
    source_type: str
    source_weight: float
    profile_id: str
    observations: Dict[str, object]
    plan_id: Optional[str] = None
    scenario_id: Optional[str] = None
    risk_decision_id: Optional[str] = None
    executor_result_id: Optional[str] = None
    parameter_snapshot: Dict[str, object] = field(default_factory=dict)
    evidence_id: str = field(default_factory=lambda: new_id("AUTOTUNE_EVIDENCE"))


@dataclass(frozen=True)
class AutotuneRecommendation:
    target_profile_id: str
    parameter_changes: Dict[str, object]
    evidence_ids: List[str]
    sample_size: int
    confidence: float
    reason: str
    target_parameter_specs: List[str] = field(default_factory=list)
    rollback_condition: Optional[str] = None
    recommendation_id: str = field(default_factory=lambda: new_id(RECOMMENDATION))
