import logging
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

logger = logging.getLogger(__name__)

class DataQuality(Enum):
    LOW = 0.5
    MEDIUM = 0.8
    HIGH = 1.0
    EXCELLENT = 1.2

class ConfidenceSystem:
    def __init__(self):
        self.default_weights = {
            "rsi": 1.0, "macd": 1.0, "bb": 1.0, "volatility": 1.0,
            "fractal": 1.0, "regime": 1.0, "volume": 1.0, "orderbook": 1.0
        }
        logger.info("ConfidenceSystem initialized")

    def calculate(self, signals: Dict[str, Any], weights_override: Optional[Dict[str, float]] = None, 
                  data_lineage: Optional[Dict[str, DataQuality]] = None) -> Tuple[float, Dict[str, Any]]:
        weights = {**self.default_weights, **(weights_override or {})}
        lineage = data_lineage or {}
        
        total_score = 0.0
        total_weight = 0.0
        breakdown = {}
        indicators = ["rsi", "macd", "bb", "volatility", "fractal", "regime", "volume", "orderbook"]

        for ind in indicators:
            if ind not in signals: continue
            signal_val = signals[ind]
            w = weights.get(ind, 1.0)
            quality_mult = 1.0
            if ind in lineage: quality_mult = lineage[ind].value
            final_weight = w * quality_mult
            contribution = signal_val * final_weight
            total_score += contribution
            total_weight += final_weight
            breakdown[ind] = {"signal": signal_val, "weight": w, "quality_mult": quality_mult, "final_weight": final_weight, "contribution": contribution}

        if total_weight == 0: return 0.0, {"error": "No valid signals"}
        raw_score = total_score / total_weight
        confidence = max(0.0, min(1.0, (raw_score + 1.0) / 2.0))
        return confidence, {"raw_score": raw_score, "total_weight": total_weight, "breakdown": breakdown, "quality_applied": len(lineage) > 0}
