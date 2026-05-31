"""Matrix data contracts.

Analyzers will later emit AnalysisResult plus ForecastContribution and/or
StateContribution; matrix engines aggregate standardized contributions without
knowing analyzer-specific payload internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from nova.analysis.models import EvidenceRef
from nova.core.evidence import CardStage, EvidenceTier, MatrixFieldRole, MatrixLayer, MatrixZoneStatus
from nova.core.ids import FORECAST, MATRIX, MATRIX_ZONE, new_id


@dataclass(frozen=True)
class ForecastContribution:
    symbol: str
    source_analysis_result_id: str
    timeframe: str
    horizon_min: int
    price_low: float
    price_high: float
    probability: float
    confidence: float
    direction: str
    weight: float = 1.0
    dependency_group: str = "unknown"
    decay_sec: int = 300
    stage: str = CardStage.RAW
    evidence_tier: str = EvidenceTier.PRIMARY
    input_matrix_id: Optional[str] = None
    feedback_depth: int = 0
    source_card_ids: List[str] = field(default_factory=list)
    parent_contribution_ids: List[str] = field(default_factory=list)
    phenomenon: Optional[str] = None
    field_shape: Optional[str] = None
    invalidation_price: Optional[float] = None
    contribution_id: str = field(default_factory=lambda: new_id(FORECAST))
    evidence_refs: List[EvidenceRef] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    payload: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MatrixZone:
    price_low: float
    price_high: float
    horizon_min: int
    scenario: str
    probability: float
    confidence: float
    contributor_ids: List[str]
    field_role: str = MatrixFieldRole.CORE
    status: str = MatrixZoneStatus.ACTIVE
    core_price_low: Optional[float] = None
    core_price_high: Optional[float] = None
    halo_price_low: Optional[float] = None
    halo_price_high: Optional[float] = None
    agreement_score: float = 0.0
    conflict_score: float = 0.0
    importance_score: float = 0.0
    source_analysis_result_ids: List[str] = field(default_factory=list)
    source_card_ids: List[str] = field(default_factory=list)
    recheck_reasons: List[str] = field(default_factory=list)
    payload: Dict[str, object] = field(default_factory=dict)
    zone_id: str = field(default_factory=lambda: new_id(MATRIX_ZONE))


@dataclass(frozen=True)
class ForecastMatrix:
    symbol: str
    cycle_id: str
    zones: List[MatrixZone]
    contributor_ids: List[str]
    source_card_ids: List[str] = field(default_factory=list)
    primary_only: bool = True
    matrix_layer: str = MatrixLayer.PRIMARY
    matrix_id: str = field(default_factory=lambda: new_id(MATRIX))


@dataclass(frozen=True)
class StateMatrix:
    symbol: str
    cycle_id: str
    trust_score: float
    volatility_state: str
    conflict_score: float
    data_quality: float
    liquidity_state: Optional[str] = None
    matrix_id: str = field(default_factory=lambda: new_id("STATE"))
