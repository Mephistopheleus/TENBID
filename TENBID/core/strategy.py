"""
Strategy Matrix - Signal Aggregation with Dynamic Weighting.

CRITICAL REQUIREMENTS:
1. News act ONLY as modifier (coefficient 0.3), NOT additive component
2. Weighted average with normalization of ACTIVE weights only
3. Strong signals from key analyzers (Fractals, Orderbook) have decisive value
4. No global news pause - system can trade on news if TA confirms
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class SignalInput:
    """Input from individual analyzer."""
    name: str
    score: float  # -1.0 to +1.0
    confidence: float  # 0.0 to 1.0
    is_active: bool  # Whether analyzer provided meaningful signal
    
@dataclass
class StrategyDecision:
    """Final decision from strategy matrix."""
    action: str  # 'LONG', 'SHORT', 'HOLD'
    final_confidence: float  # 0.0 to 1.0
    weighted_score: float  # Raw weighted sum before normalization
    active_signals_count: int
    dominant_signal: str  # Which analyzer had strongest impact
    news_modifier: float  # News impact (-0.3 to +0.3)
    base_score: float  # Score before news modification
    reasoning: Dict[str, float]  # Breakdown by analyzer

class StrategyMatrix:
    def __init__(self, default_weights: Optional[Dict[str, float]] = None):
        """
        Initialize strategy matrix with default or custom weights.
        
        Weights represent trust in each analyzer type.
        Higher weight = more influence on final decision.
        """
        self.default_weights = default_weights or {
            "btc_correlation": 1.5,
            "fractal": 1.3,
            "orderbook": 1.2,
            "pattern": 1.4,
            "regime": 2.0,
            "volume": 1.1,
            "trend": 1.0
        }
        self.current_weights = self.default_weights.copy()
        
        # CRITICAL: News coefficient - limits news impact to max 30%
        self.NEWS_MODIFIER_COEFFICIENT = 0.3
        
        # Thresholds for action
        self.LONG_THRESHOLD = 0.65
        self.SHORT_THRESHOLD = -0.65
        self.HOLD_ZONE = (-0.3, 0.3)  # Confidence zone where we hold
        
        logger.info(f"StrategyMatrix initialized with NEWS_MODIFIER_COEFFICIENT={self.NEWS_MODIFIER_COEFFICIENT}")
    
    def update_weights(self, new_weights: Dict[str, float]):
        """Update weights from Autotuner."""
        self.current_weights.update(new_weights)
        logger.info(f"Strategy weights updated: {new_weights}")
    
    def aggregate_signals(
        self,
        analyzer_signals: Dict[str, SignalInput],
        news_score: float = 0.0,
        news_confidence: float = 0.0
    ) -> StrategyDecision:
        """
        CRITICAL: Aggregate all analyzer signals with proper weighting.
        
        FORMULA: Final_Confidence = Base_Weighted_Score + (News_Score * News_Confidence * 0.3)
        
        Key principles:
        1. Only ACTIVE signals participate in weighting
        2. Strong signals from key analyzers can dominate
        3. News acts as modifier, not trigger
        4. No global pause - always return a decision
        """
        # Filter active signals
        active_signals = {
            name: sig for name, sig in analyzer_signals.items() 
            if sig.is_active and abs(sig.score) > 0.05
        }
        
        if not active_signals:
            logger.debug("No active signals, returning HOLD")
            return StrategyDecision(
                action='HOLD',
                final_confidence=0.0,
                weighted_score=0.0,
                active_signals_count=0,
                dominant_signal='NONE',
                news_modifier=0.0,
                base_score=0.0,
                reasoning={}
            )
        
        # Calculate weighted sum with NORMALIZATION of active weights only
        weighted_sum = 0.0
        total_active_weight = 0.0
        reasoning = {}
        
        strongest_signal = {'name': 'NONE', 'abs_score': 0.0}
        
        for name, signal in active_signals.items():
            # Get weight for this analyzer
            weight_key = name.lower().replace('_analyzer', '').replace('signal', '')
            weight = self.current_weights.get(weight_key, 1.0)
            
            # Weighted contribution
            contribution = signal.score * weight * signal.confidence
            weighted_sum += contribution
            total_active_weight += weight * signal.confidence
            
            reasoning[name] = round(contribution, 4)
            
            # Track dominant signal
            if abs(signal.score) > strongest_signal['abs_score']:
                strongest_signal = {'name': name, 'abs_score': abs(signal.score)}
        
        # Normalize by active weights (NOT all weights)
        if total_active_weight > 0:
            base_score = weighted_sum / total_active_weight
        else:
            base_score = 0.0
        
        # CRITICAL: News as MODIFIER only (formula: Base + News * Conf * 0.3)
        # News cannot drive the decision alone, only modify existing TA signal
        news_modifier = news_score * news_confidence * self.NEWS_MODIFIER_COEFFICIENT
        news_modifier = max(-0.3, min(0.3, news_modifier))  # Clamp to [-0.3, +0.3]
        
        final_score = base_score + news_modifier
        
        # Determine action based on thresholds
        if final_score >= self.LONG_THRESHOLD:
            action = 'LONG'
        elif final_score <= self.SHORT_THRESHOLD:
            action = 'SHORT'
        elif final_score > self.HOLD_ZONE[1] or final_score < self.HOLD_ZONE[0]:
            # Weak signal zone - check if strong dominant signal exists
            if strongest_signal['abs_score'] > 0.8:
                # Strong single analyzer signal - allow trade even if others silent
                action = 'LONG' if final_score > 0 else 'SHORT'
                logger.info(f"Strong dominant signal from {strongest_signal['name']} overriding weak aggregate")
            else:
                action = 'HOLD'
        else:
            action = 'HOLD'
        
        # Convert score to confidence (0-1 range)
        final_confidence = min(1.0, abs(final_score))
        
        decision = StrategyDecision(
            action=action,
            final_confidence=round(final_confidence, 4),
            weighted_score=round(weighted_sum, 4),
            active_signals_count=len(active_signals),
            dominant_signal=strongest_signal['name'],
            news_modifier=round(news_modifier, 4),
            base_score=round(base_score, 4),
            reasoning=reasoning
        )
        
        # Log decision details
        if action != 'HOLD':
            logger.info(
                f"Strategy Decision: {action} (conf={final_confidence:.2f}, "
                f"base={base_score:.3f}, news_mod={news_modifier:.3f}, "
                f"dominant={strongest_signal['name']})"
            )
        else:
            logger.debug(
                f"Strategy HOLD: base={base_score:.3f}, news_mod={news_modifier:.3f}, "
                f"active_signals={len(active_signals)}"
            )
        
        return decision
    
    def get_adjusted_thresholds(self, regime_type: str) -> Tuple[float, float]:
        """
        Adjust entry thresholds based on market regime.
        
        In ranging markets: stricter thresholds (avoid false breakouts)
        In trending markets: slightly looser thresholds (catch trends early)
        """
        if regime_type == 'RANGING':
            # Stricter thresholds in choppy markets
            return (0.75, -0.75)
        elif regime_type == 'STRONG_TREND':
            # Looser thresholds when trend is clear
            return (0.55, -0.55)
        else:
            # Default thresholds
            return (self.LONG_THRESHOLD, self.SHORT_THRESHOLD)
    
    def should_override_with_strong_signal(
        self,
        signal_name: str,
        signal_score: float,
        current_action: str
    ) -> bool:
        """
        Check if a single strong analyzer signal should override the aggregate.
        
        This prevents dilution of strong signals when other analyzers are neutral.
        """
        # Key analyzers that can override
        KEY_ANALYZERS = ['fractal', 'orderbook', 'pattern']
        
        if signal_name.lower() not in KEY_ANALYZERS:
            return False
        
        if abs(signal_score) < 0.85:
            return False
        
        # If aggregate says HOLD but key analyzer has very strong signal
        if current_action == 'HOLD' and abs(signal_score) >= 0.9:
            logger.info(f"Strong signal override: {signal_name} score {signal_score}")
            return True
        
        return False
