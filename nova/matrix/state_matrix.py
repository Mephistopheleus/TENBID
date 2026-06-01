"""State matrix engine.

Builds trust/context around the sparse evidence field. It does not calculate a
market action; it summarizes whether the current picture is fresh, conflicted,
liquid enough and worth rechecking.
"""

from __future__ import annotations

from typing import Iterable

from nova.analysis.models import StateContribution
from nova.core.evidence import MatrixFieldRole
from nova.data.models import MarketSnapshot
from nova.matrix.models import ForecastMatrix, StateMatrix


class StateMatrixEngine:
    def build(
        self,
        *,
        cycle_id: str,
        symbol: str,
        market_snapshot: MarketSnapshot | None,
        forecast_matrix: ForecastMatrix | None,
        state_contributions: Iterable[StateContribution] | None = None,
    ) -> StateMatrix:
        state_contributions = list(state_contributions or [])
        data_quality = market_snapshot.quality.score if market_snapshot is not None else 0.0
        liquidity_state = self._liquidity_state(market_snapshot)
        tension_zones = [
            zone
            for zone in (forecast_matrix.zones if forecast_matrix is not None else [])
            if zone.field_role == MatrixFieldRole.TENSION
        ]
        conflict_score = max([zone.conflict_score for zone in tension_zones], default=0.0)
        recheck_reasons = sorted({reason for zone in tension_zones for reason in zone.recheck_reasons})
        trust_score = self._trust_score()
        return StateMatrix(
            symbol=symbol.upper(),
            cycle_id=cycle_id,
            trust_score=trust_score,
            volatility_state="not_evaluated",
            conflict_score=conflict_score,
            data_quality=data_quality,
            liquidity_state=liquidity_state,
            payload={
                "not_market_action": True,
                "market_snapshot_id": market_snapshot.snapshot_id if market_snapshot else None,
                "forecast_matrix_id": forecast_matrix.matrix_id if forecast_matrix else None,
                "zone_count": len(forecast_matrix.zones) if forecast_matrix else 0,
                "tension_zone_count": len(tension_zones),
                "recheck_reasons": recheck_reasons,
                "state_contribution_count": len(state_contributions),
                "trust_score_semantics": "initial_context_trust_not_data_quality_and_not_trade_permission",
                "orderbook_snapshot_id": market_snapshot.orderbook.snapshot_id
                if market_snapshot and market_snapshot.orderbook
                else None,
            },
        )

    @staticmethod
    def _liquidity_state(snapshot: MarketSnapshot | None) -> str:
        if snapshot is None or snapshot.orderbook is None:
            return "orderbook_not_loaded"
        if not snapshot.orderbook.quality.is_usable:
            return "orderbook_unusable"
        best_bid = snapshot.orderbook.best_bid()
        best_ask = snapshot.orderbook.best_ask()
        if best_bid is None or best_ask is None:
            return "orderbook_empty"
        if best_ask.price < best_bid.price:
            return "orderbook_crossed"
        return "orderbook_available"

    @staticmethod
    def _trust_score() -> float:
        return 0.1
