"""Analyzer output and evidence contracts.

Future analyzers may keep arbitrary module-specific payloads, but NOVA reasons
over standardized AnalysisResult, ForecastContribution and StateContribution
lineage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from nova.core.evidence import CardStage, EvidenceTier
from nova.core.ids import ANALYSIS, new_id


@dataclass(frozen=True)
class EvidenceRef:
    evidence_type: str
    source_id: str
    description: Optional[str] = None


class AnalysisStatus:
    OK = "OK"
    NO_DATA = "NO_DATA"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"


@dataclass(frozen=True)
class AnalysisResult:
    analyzer_name: str
    analyzer_version: str
    symbol: str
    timeframe: str
    run_id: str
    cycle_id: str
    market_snapshot_id: Optional[str]
    confidence: float
    quality: float
    status: str
    payload: Dict[str, Any] = field(default_factory=dict)
    parameters_used: Dict[str, Any] = field(default_factory=dict)
    input_ids: List[str] = field(default_factory=list)
    dependency_group: str = "unknown"
    stage: str = CardStage.RAW
    evidence_tier: str = EvidenceTier.PRIMARY
    input_matrix_id: Optional[str] = None
    parent_analysis_result_ids: List[str] = field(default_factory=list)
    parent_card_ids: List[str] = field(default_factory=list)
    feedback_depth: int = 0
    evidence_refs: List[EvidenceRef] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    analysis_result_id: str = field(default_factory=lambda: new_id(ANALYSIS))


@dataclass(frozen=True)
class StateContribution:
    source_analysis_result_id: str
    state_type: str
    value: Any
    confidence: float
    severity: str
    ttl_sec: int = 300
    stage: str = CardStage.RAW
    evidence_tier: str = EvidenceTier.PRIMARY
    input_matrix_id: Optional[str] = None
    feedback_depth: int = 0
    source_card_ids: List[str] = field(default_factory=list)
    evidence_refs: List[EvidenceRef] = field(default_factory=list)
    state_contribution_id: str = field(default_factory=lambda: new_id("STATE_CONTRIB"))
