"""Matrix data contracts.

Analyzers will later emit ForecastContribution and StateContribution; matrix engines aggregate them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from nova.core.ids import FORECAST, MATRIX, new_id


@dataclass(frozen=True)
class ForecastContribution:
    symbol: str
    source_analysis_id: str
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
    contribution_id: str = field(default_factory=lambda: new_id(FORECAST))
    evidence: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MatrixZone:
    price_low: float
    price_high: float
    horizon_min: int
    scenario: str
    probability: float
    confidence: float
    contributor_ids: List[str]


@dataclass(frozen=True)
class ForecastMatrix:
    symbol: str
    cycle_id: str
    zones: List[MatrixZone]
    contributor_ids: List[str]
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

