"""
TENBID - Confidence Level Distribution Module
Trust score system for trade decision making
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import time

class ConfidenceLevel(Enum):
    VERY_LOW = "VERY_LOW"      # 0-20
    LOW = "LOW"                # 21-40
    MEDIUM = "MEDIUM"          # 41-60
    HIGH = "HIGH"              # 61-80
    VERY_HIGH = "VERY_HIGH"    # 81-100

@dataclass
class TrustFactor:
    """Individual factor contributing to confidence"""
    name: str
    weight: float           # Importance of this factor (0.0-1.0)
    score: float            # Current score (0.0-100.0)
    last_updated: int
    history: List[float]    # Recent score history

@dataclass
class TradeConfidence:
    """Complete confidence assessment for a trade"""
    overall_score: float
    level: ConfidenceLevel
    factors: Dict[str, TrustFactor]
    recommendation: str
    timestamp: int

class ConfidenceSystem:
    def __init__(self):
        self.trust_factors: Dict[str, TrustFactor] = {}
        self.min_trade_score = 70.0  # Minimum score to execute trade
        self.max_history_length = 50
        
        # Initialize default trust factors
        self._init_default_factors()
    
    def _init_default_factors(self):
        """Initialize default trust factors for scalping"""
        default_factors = {
            "technical_analysis": TrustFactor(
                name="Technical Analysis",
                weight=0.25,
                score=50.0,
                last_updated=int(time.time()),
                history=[]
            ),
            "probability_field": TrustFactor(
                name="Probability Field",
                weight=0.25,
                score=50.0,
                last_updated=int(time.time()),
                history=[]
            ),
            "market_conditions": TrustFactor(
                name="Market Conditions",
                weight=0.20,
                score=50.0,
                last_updated=int(time.time()),
                history=[]
            ),
            "risk_assessment": TrustFactor(
                name="Risk Assessment",
                weight=0.15,
                score=50.0,
                last_updated=int(time.time()),
                history=[]
            ),
            "shadow_validation": TrustFactor(
                name="Shadow Validation",
                weight=0.15,
                score=50.0,
                last_updated=int(time.time()),
                history=[]
            )
        }
        
        for name, factor in default_factors.items():
            self.trust_factors[name] = factor
    
    def update_factor_score(self, factor_name: str, score: float, weight: Optional[float] = None):
        """Update score for a specific trust factor"""
        if factor_name not in self.trust_factors:
            # Create new factor if doesn't exist
            self.trust_factors[factor_name] = TrustFactor(
                name=factor_name,
                weight=weight if weight else 0.1,
                score=score,
                last_updated=int(time.time()),
                history=[]
            )
            return
        
        factor = self.trust_factors[factor_name]
        factor.score = max(0.0, min(100.0, score))  # Clamp to 0-100
        factor.last_updated = int(time.time())
        
        # Add to history
        factor.history.append(factor.score)
        if len(factor.history) > self.max_history_length:
            factor.history = factor.history[-self.max_history_length:]
        
        # Update weight if provided
        if weight is not None:
            factor.weight = max(0.0, min(1.0, weight))
    
    def calculate_overall_score(self) -> float:
        """Calculate weighted overall confidence score"""
        if not self.trust_factors:
            return 0.0
        
        total_weight = sum(f.weight for f in self.trust_factors.values())
        if total_weight == 0:
            return 0.0
        
        weighted_sum = sum(f.score * f.weight for f in self.trust_factors.values())
        overall_score = weighted_sum / total_weight
        
        return round(overall_score, 2)
    
    def get_confidence_level(self, score: float) -> ConfidenceLevel:
        """Convert numeric score to confidence level"""
        if score < 20:
            return ConfidenceLevel.VERY_LOW
        elif score < 40:
            return ConfidenceLevel.LOW
        elif score < 60:
            return ConfidenceLevel.MEDIUM
        elif score < 80:
            return ConfidenceLevel.HIGH
        else:
            return ConfidenceLevel.VERY_HIGH
    
    def get_recommendation(self, score: float) -> str:
        """Get trading recommendation based on confidence score"""
        if score >= 90:
            return "STRONG BUY/SELL - Execute with maximum position"
        elif score >= 80:
            return "BUY/SELL - Execute with normal position"
        elif score >= 70:
            return "WEAK BUY/SELL - Execute with reduced position"
        elif score >= 60:
            return "HOLD - Wait for better opportunity"
        elif score >= 40:
            return "UNCERTAIN - Reduce exposure"
        elif score >= 20:
            return "AVOID - High risk environment"
        else:
            return "EXIT - Close all positions immediately"
    
    def get_trend_analysis(self, factor_name: str) -> str:
        """Analyze trend of a specific factor"""
        if factor_name not in self.trust_factors:
            return "UNKNOWN"
        
        factor = self.trust_factors[factor_name]
        if len(factor.history) < 3:
            return "INSUFFICIENT_DATA"
        
        recent = factor.history[-3:]
        if all(recent[i] < recent[i+1] for i in range(len(recent)-1)):
            return "IMPROVING"
        elif all(recent[i] > recent[i+1] for i in range(len(recent)-1)):
            return "DETERIORATING"
        else:
            return "STABLE"
    
    def generate_trade_confidence(self) -> TradeConfidence:
        """Generate complete trade confidence assessment"""
        overall_score = self.calculate_overall_score()
        level = self.get_confidence_level(overall_score)
        recommendation = self.get_recommendation(overall_score)
        
        return TradeConfidence(
            overall_score=overall_score,
            level=level,
            factors=self.trust_factors.copy(),
            recommendation=recommendation,
            timestamp=int(time.time())
        )
    
    def should_execute_trade(self) -> bool:
        """Determine if trade should be executed based on confidence"""
        overall_score = self.calculate_overall_score()
        return overall_score >= self.min_trade_score
    
    def get_detailed_report(self) -> Dict:
        """Generate detailed confidence report"""
        report = {
            "timestamp": int(time.time()),
            "overall_score": self.calculate_overall_score(),
            "confidence_level": self.get_confidence_level(self.calculate_overall_score()).value,
            "recommendation": self.get_recommendation(self.calculate_overall_score()),
            "should_trade": self.should_execute_trade(),
            "factors": {},
            "thresholds": {
                "min_trade_score": self.min_trade_score,
                "strong_signal": 90,
                "good_signal": 80,
                "weak_signal": 70
            }
        }
        
        for name, factor in self.trust_factors.items():
            report["factors"][name] = {
                "score": factor.score,
                "weight": factor.weight,
                "trend": self.get_trend_analysis(name),
                "weighted_contribution": round(factor.score * factor.weight, 2)
            }
        
        return report
    
    def reset_factors(self):
        """Reset all factor scores to neutral"""
        for factor in self.trust_factors.values():
            factor.score = 50.0
            factor.history = []
            factor.last_updated = int(time.time())


if __name__ == "__main__":
    # Test confidence system
    print("Testing Confidence System...")
    
    system = ConfidenceSystem()
    
    # Simulate updating various factors
    system.update_factor_score("technical_analysis", 85.0)
    system.update_factor_score("probability_field", 72.0)
    system.update_factor_score("market_conditions", 65.0)
    system.update_factor_score("risk_assessment", 90.0)
    system.update_factor_score("shadow_validation", 78.0)
    
    # Generate report
    report = system.get_detailed_report()
    
    print("\n=== CONFIDENCE REPORT ===")
    print(f"Overall Score: {report['overall_score']}/100")
    print(f"Confidence Level: {report['confidence_level']}")
    print(f"Recommendation: {report['recommendation']}")
    print(f"Should Trade: {'YES' if report['should_trade'] else 'NO'}")
    
    print("\n--- Factor Breakdown ---")
    for factor_name, factor_data in report['factors'].items():
        print(f"\n{factor_name}:")
        print(f"  Score: {factor_data['score']}")
        print(f"  Weight: {factor_data['weight']*100:.0f}%")
        print(f"  Trend: {factor_data['trend']}")
        print(f"  Contribution: {factor_data['weighted_contribution']}")
