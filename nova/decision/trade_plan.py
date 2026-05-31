"""Canonical TradePlan contract.

TradePlan is the later calculator/risk-manager output envelope. Data, analyzers
and matrix must not fill it directly. Current runtime uses HOLD only as a safe
placeholder while the calculation layer is not connected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from nova.core.ids import PLAN, new_id


@dataclass(frozen=True)
class CostEstimate:
    commission_pct: float
    spread_pct: float
    slippage_pct: float
    total_cost_pct: float
    breakeven_move_pct: float


@dataclass(frozen=True)
class TradePlan:
    decision: str
    symbol: str
    reason: str
    profile_id: str
    forecast_matrix_id: Optional[str] = None
    state_matrix_id: Optional[str] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    rr_ratio: Optional[float] = None
    confidence: float = 0.0
    net_expected_edge_pct: float = 0.0
    costs: Optional[CostEstimate] = None
    dynamics_summary: Dict[str, object] = field(default_factory=dict)
    plan_id: str = field(default_factory=lambda: new_id(PLAN))
