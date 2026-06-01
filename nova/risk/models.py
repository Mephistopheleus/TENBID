"""Risk decision contracts for the TESTNET execution path."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from nova.core.ids import new_id


class RiskDecisionStatus:
    APPROVED = "APPROVED"
    APPROVED_WITH_WARNINGS = "APPROVED_WITH_WARNINGS"
    SHADOW_FIRST_REQUIRED = "SHADOW_FIRST_REQUIRED"
    REJECTED = "REJECTED"
    REDUCED = "REDUCED"
    REQUIRES_RECHECK = "REQUIRES_RECHECK"


@dataclass(frozen=True)
class RiskDecision:
    plan_id: str
    status: str
    reason: str
    approved_for_executor: bool
    profile_id: str
    state_matrix_id: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    hard_blocks: List[str] = field(default_factory=list)
    adjusted_size_factor: float = 1.0
    payload: Dict[str, object] = field(default_factory=dict)
    risk_decision_id: str = field(default_factory=lambda: new_id("RISK"))
