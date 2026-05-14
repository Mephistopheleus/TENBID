"""
TENBID - Probability Field Builder Module
Constructs multi-dimensional probability maps for trade outcomes
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

class SignalStrength(Enum):
    VERY_WEAK = 1
    WEAK = 2
    NEUTRAL = 3
    STRONG = 4
    VERY_STRONG = 5

@dataclass
class ProbabilityNode:
    """Single node in the probability field"""
    price_level: float
    probability_up: float
    probability_down: float
    confidence: float
    signal_strength: SignalStrength
    contributing_factors: Dict[str, float]

class ProbabilityFieldBuilder:
    def __init__(self, grid_size: int = 21, price_range_pct: float = 2.0):
        self.grid_size = grid_size  # Must be odd for center pivot
        self.price_range_pct = price_range_pct
        self.field_matrix = np.zeros((grid_size, grid_size))
        self.current_price = 0.0
        self.price_levels = []
        self.time_decay_factor = 0.95
        
    def set_current_price(self, price: float):
        """Set the current market price as center of field"""
        self.current_price = price
        self._build_price_levels()
        
    def _build_price_levels(self):
        """Build price level grid around current price"""
        if self.current_price == 0:
            return
            
        range_amount = self.current_price * (self.price_range_pct / 100)
        step = (2 * range_amount) / (self.grid_size - 1)
        
        self.price_levels = []
        center_idx = self.grid_size // 2
        
        for i in range(self.grid_size):
            level = self.current_price - (center_idx * step) + (i * step)
            self.price_levels.append(level)
    
    def update_probability(self, price_level: float, direction: str, 
                          probability: float, confidence: float,
                          factor_name: str, factor_weight: float):
        """Update probability at specific price level"""
        if not self.price_levels:
            return
        
        # Find closest price level index
        idx = min(range(len(self.price_levels)), 
                 key=lambda i: abs(self.price_levels[i] - price_level))
        
        time_idx = 0  # Could be extended for time dimension
        
        # Apply weighted update
        old_value = self.field_matrix[idx, time_idx]
        update_value = probability * confidence * factor_weight
        
        if direction == "up":
            self.field_matrix[idx, time_idx] = max(old_value, update_value)
        elif direction == "down":
            self.field_matrix[idx, time_idx] = min(old_value, -update_value)
    
    def apply_technical_signal(self, indicator_name: str, value: float, 
                               threshold_low: float, threshold_high: float,
                               weight: float = 1.0):
        """
        Apply technical indicator signal to probability field
        Values above threshold_high increase up probability
        Values below threshold_low increase down probability
        """
        if value > threshold_high:
            strength = SignalStrength.VERY_STRONG
            direction = "up"
            probability = min(1.0, (value - threshold_high) / threshold_high + 0.5)
        elif value < threshold_low:
            strength = SignalStrength.VERY_STRONG
            direction = "down"
            probability = min(1.0, (threshold_low - value) / threshold_low + 0.5)
        else:
            strength = SignalStrength.NEUTRAL
            direction = "neutral"
            probability = 0.5
        
        # Apply to center of field (current price area)
        center_idx = self.grid_size // 2
        center_price = self.price_levels[center_idx] if self.price_levels else self.current_price
        
        self.update_probability(
            price_level=center_price,
            direction=direction,
            probability=probability,
            confidence=0.8,
            factor_name=indicator_name,
            factor_weight=weight
        )
        
        return strength, direction, probability
    
    def calculate_expectation(self) -> Tuple[float, float, float]:
        """
        Calculate expected move from probability field
        Returns: (expected_direction, expected_magnitude, confidence)
        """
        if len(self.price_levels) == 0:
            return (0.0, 0.0, 0.0)
        
        center_idx = self.grid_size // 2
        
        # Sum probabilities above and below center
        up_prob = np.sum(self.field_matrix[center_idx+1:, 0])
        down_prob = abs(np.sum(self.field_matrix[:center_idx, 0]))
        
        total_prob = up_prob + down_prob
        if total_prob == 0:
            return (0.0, 0.0, 0.0)
        
        # Calculate weighted average price target
        if up_prob > down_prob:
            direction = 1.0
            weighted_sum = sum(self.price_levels[i] * self.field_matrix[i, 0] 
                             for i in range(center_idx+1, self.grid_size))
        else:
            direction = -1.0
            weighted_sum = sum(self.price_levels[i] * abs(self.field_matrix[i, 0]) 
                             for i in range(center_idx))
        
        if total_prob > 0:
            expected_price = weighted_sum / total_prob
            magnitude = abs(expected_price - self.current_price) / self.current_price * 100
        else:
            magnitude = 0.0
        
        confidence = min(1.0, total_prob / (self.grid_size * 2))
        
        return (direction, magnitude, confidence)
    
    def get_high_probability_zones(self, threshold: float = 0.7) -> List[Dict]:
        """Get price levels with high probability"""
        zones = []
        center_idx = self.grid_size // 2
        
        for i in range(self.grid_size):
            prob = abs(self.field_matrix[i, 0])
            if prob >= threshold:
                zone_type = "resistance" if i < center_idx else "support"
                zones.append({
                    "price": self.price_levels[i],
                    "probability": prob,
                    "type": zone_type,
                    "distance_pct": abs(self.price_levels[i] - self.current_price) / self.current_price * 100
                })
        
        return sorted(zones, key=lambda x: x["probability"], reverse=True)
    
    def apply_time_decay(self):
        """Apply time decay to all probabilities"""
        self.field_matrix *= self.time_decay_factor
    
    def reset_field(self):
        """Reset probability field"""
        self.field_matrix = np.zeros((self.grid_size, self.grid_size))
    
    def get_field_summary(self) -> Dict:
        """Get comprehensive field summary"""
        direction, magnitude, confidence = self.calculate_expectation()
        high_prob_zones = self.get_high_probability_zones()
        
        return {
            "current_price": self.current_price,
            "expected_direction": "UP" if direction > 0 else "DOWN" if direction < 0 else "NEUTRAL",
            "expected_magnitude_pct": magnitude,
            "confidence": confidence,
            "high_probability_zones": high_prob_zones[:5],  # Top 5 zones
            "field_stats": {
                "max_probability": float(np.max(self.field_matrix)),
                "min_probability": float(np.min(self.field_matrix)),
                "mean_probability": float(np.mean(np.abs(self.field_matrix))),
                "total_energy": float(np.sum(np.abs(self.field_matrix)))
            }
        }


if __name__ == "__main__":
    # Test probability field
    field = ProbabilityFieldBuilder(grid_size=21, price_range_pct=2.0)
    field.set_current_price(50000.0)
    
    print("Testing Probability Field Builder...")
    print(f"Current Price: ${field.current_price}")
    print(f"Price Levels: {len(field.price_levels)}")
    
    # Simulate technical signals
    field.apply_technical_signal("RSI", 25, 30, 70, weight=1.2)  # Oversold
    field.apply_technical_signal("MACD", 0.8, 0.5, -0.5, weight=1.0)  # Bullish
    field.apply_technical_signal("Volatility", 0.03, 0.02, 0.05, weight=0.8)
    
    summary = field.get_field_summary()
    print("\nProbability Field Summary:")
    for key, value in summary.items():
        if key != "high_probability_zones":
            print(f"  {key}: {value}")
    
    print("\nHigh Probability Zones:")
    for zone in summary["high_probability_zones"]:
        print(f"  {zone['type']}: ${zone['price']:.2f} ({zone['probability']:.2%})")
