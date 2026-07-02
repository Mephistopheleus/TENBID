"""Build bounded scenario candidates from Matrix and State context.

This module implements the NEW architecture:
1. Receives full Market Picture (ForecastMatrix + StateMatrix).
2. Evaluates ASYMMETRY based on probability fields and confidence zones.
3. Calculates SPECIFIC COORDINATES: Entry, Stop, TakeProfit, Leverage.
4. Outputs a concrete Trade Hypothesis with R/R ratio and expected PnL.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import math

from nova.data.models import MarketSnapshot
from nova.matrix.models import ForecastMatrix, MatrixZone, StateMatrix
from nova.scenario.models import ScenarioCandidate, ScenarioStatus, ScenarioBuildResult


class ScenarioBuilder:
    """Converts the market probability field into a computable trade hypothesis.

    Unlike the old signal-based approach, this builder:
    - Analyzes the ENTIRE probability field from the Matrix.
    - Identifies zones of high asymmetry (high prob, low risk).
    - Calculates precise entry, stop-loss, and take-profit levels.
    - Estimates required leverage and position size based on volatility.
    - Does NOT make final decisions (that's RiskManager's job).
    """

    def build(
        self,
        *,
        cycle_id: str,
        forecast_matrix: Optional[ForecastMatrix],
        state_matrix: Optional[StateMatrix],
        market_snapshot: Optional[MarketSnapshot],
        profile_values: Optional[Dict[str, Any]] = None,
    ) -> ScenarioBuildResult:
        profile_values = profile_values or {}
        
        # Validate inputs
        if market_snapshot is None:
            return self._no_scenario("missing_market_snapshot")
        if forecast_matrix is None:
            return self._no_scenario("missing_forecast_matrix")
        if state_matrix is None:
            return self._no_scenario("missing_state_matrix")

        reference_price = self._get_reference_price(market_snapshot)
        if reference_price is None or reference_price <= 0.0:
            return self._no_scenario("invalid_reference_price")

        # Analyze the full probability field
        best_opportunity = self._find_best_asymmetry(
            forecast_matrix=forecast_matrix,
            state_matrix=state_matrix,
            current_price=reference_price
        )

        if not best_opportunity:
            return self._no_scenario("no_asymmetric_opportunity_found")

        # Calculate specific trade coordinates
        scenario = self._calculate_trade_coordinates(
            opportunity=best_opportunity,
            current_price=reference_price,
            volatility=getattr(market_snapshot, 'volatility_atr_14', 0.01) or 0.01
        )

        return ScenarioBuildResult(
            status=ScenarioStatus.CALCULATED,
            candidates=[scenario],
            meta={
                "matrix_zones_analyzed": len(forecast_matrix.zones),
                "confidence_score": scenario.confidence,
                "expected_rr": scenario.risk_reward_ratio
            }
        )

    def _get_reference_price(self, snapshot: MarketSnapshot) -> Optional[float]:
        """Get the latest close price as reference."""
        if snapshot.candles and len(snapshot.candles) > 0:
            return snapshot.candles[-1].close
        return None

    def _find_best_asymmetry(
        self,
        forecast_matrix: ForecastMatrix,
        state_matrix: StateMatrix,
        current_price: float
    ) -> Optional[Dict[str, Any]]:
        """Scan the probability field for the best risk/reward asymmetry."""
        best_zone = None
        max_asymmetry_score = -1.0

        for zone in forecast_matrix.zones:
            # Calculate asymmetry score: (Probability * Confidence) / Distance_to_Price
            distance = abs(zone.price_level - current_price) / current_price
            if distance == 0:
                continue
            
            # Weighted probability from matrix data
            weighted_prob = zone.probability * zone.confidence_weight
            
            # Asymmetry: High prob + High confidence + Close price = Good
            score = (weighted_prob * zone.confidence_weight) / (distance + 0.001)

            if score > max_asymmetry_score:
                max_asymmetry_score = score
                best_zone = zone

        if not best_zone or max_asymmetry_score < 0.5: # Threshold for minimal interest
            return None

        return {
            "zone": best_zone,
            "direction": best_zone.direction, # LONG or SHORT
            "probability": best_zone.probability,
            "confidence": best_zone.confidence_weight,
            "score": max_asymmetry_score
        }

    def _calculate_trade_coordinates(
        self,
        opportunity: Dict[str, Any],
        current_price: float,
        volatility: float
    ) -> ScenarioCandidate:
        """Calculate precise Entry, Stop, TakeProfit, and Leverage."""
        zone = opportunity["zone"]
        direction = opportunity["direction"]
        
        # Logic for coordinate calculation based on zone type
        if direction == "LONG":
            entry_price = zone.price_level * 1.001 # Slight buffer above zone
            stop_loss_price = zone.support_level * 0.995 # Below support
            take_profit_price = zone.resistance_level * 0.995 # Below next resistance
            
            # Dynamic RR calculation
            risk_dist = entry_price - stop_loss_price
            reward_dist = take_profit_price - entry_price
            
        else: # SHORT
            entry_price = zone.price_level * 0.999 # Slight buffer below zone
            stop_loss_price = zone.resistance_level * 1.005 # Above resistance
            take_profit_price = zone.support_level * 1.005 # Above next support
            
            risk_dist = stop_loss_price - entry_price
            reward_dist = entry_price - take_profit_price

        # Prevent division by zero and ensure logical stops
        if risk_dist <= 0:
            risk_dist = current_price * 0.01 # Fallback 1% risk
        if reward_dist <= 0:
            reward_dist = risk_dist * 2 # Fallback 1:2 RR

        rr_ratio = reward_dist / risk_dist
        
        # Calculate optimal leverage based on volatility and RR
        # Higher volatility -> Lower leverage. Higher RR -> Can afford higher leverage.
        base_leverage = 10.0
        vol_factor = max(0.5, 1.0 - (volatility / current_price) * 100)
        optimal_leverage = min(20.0, base_leverage * vol_factor * (rr_ratio / 2.0))

        return ScenarioCandidate(
            cycle_id=cycle_id, # Will be filled by caller
            direction=direction,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            leverage=round(optimal_leverage, 1),
            risk_reward_ratio=round(rr_ratio, 2),
            confidence=opportunity["probability"],
            reason=f"Asymmetry detected at {direction} zone. Prob: {opportunity['probability']:.2f}, Score: {opportunity['score']:.2f}",
            meta={
                "zone_id": zone.zone_id,
                "matrix_confidence": opportunity["confidence"],
                "volatility_used": volatility
            }
        )

    def _no_scenario(self, reason: str, meta: Optional[Dict] = None) -> ScenarioBuildResult:
        return ScenarioBuildResult(
            status=ScenarioStatus.NO_OPPORTUNITY,
            candidates=[],
            meta={"reason": reason, **(meta or {})}
        )
