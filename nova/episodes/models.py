"""Market video models.

Episodes allow the system to learn from dynamics, not isolated snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from nova.core.ids import new_id


@dataclass(frozen=True)
class DynamicsContext:
    episode_id: str
    lookback_min: int
    price_velocity: Optional[float] = None
    volatility_trend: Optional[float] = None
    volume_trend: Optional[float] = None
    matrix_probability_slope: Optional[float] = None
    confidence_slope: Optional[float] = None
    state_conflict_trend: Optional[float] = None
    spread_trend: Optional[float] = None
    liquidity_stability: Optional[float] = None
    extra: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketEpisode:
    symbol: str
    start_time: str
    end_time: str
    related_plan_id: Optional[str] = None
    event_ids: List[str] = field(default_factory=list)
    payload: Dict[str, object] = field(default_factory=dict)
    episode_id: str = field(default_factory=lambda: new_id("EPISODE"))
