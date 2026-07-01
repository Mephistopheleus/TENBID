"""Smart Trailing Stop - adaptive trailing based on market conditions and data quality"""

from typing import Dict, Optional
from core.analysis_context import AnalysisContext


class SmartTrailing:
    def __init__(self, config):
        self.enabled = config.getboolean('TRAILING', 'enabled')
        self.activation_profit_pct = config.getfloat('TRAILING', 'activation_profit_pct')
        self.initial_step_pct = config.getfloat('TRAILING', 'initial_step_pct')
        self.atr_multiplier = config.getfloat('TRAILING', 'atr_multiplier')
        self.min_step_pct = config.getfloat('TRAILING', 'min_step_pct')
    
    def calculate_trail(self, entry_price: float, current_price: float, atr: float, 
                       high_since_entry: float, context: AnalysisContext = None) -> Optional[Dict]:
        """
        Calculate trailing stop level with regime and pattern adjustments.
        
        Args:
            entry_price: Entry price of the position
            current_price: Current market price
            atr: Average True Range value
            high_since_entry: Highest price since entry
            context: Optional AnalysisContext for regime/pattern adjustments
            
        Returns:
            Dictionary with trail parameters or None if not activated
        """
        if not self.enabled:
            return None
        
        # Check if activation profit reached
        profit_pct = (current_price - entry_price) / entry_price * 100
        if profit_pct < self.activation_profit_pct:
            return None
        
        # Base dynamic step based on ATR
        atr_step = (atr / current_price * 100) * self.atr_multiplier if atr > 0 else self.initial_step_pct
        base_step_pct = max(self.min_step_pct, atr_step)
        
        # Adjust step based on Market Regime (if context provided)
        regime_adjustment = 1.0
        regime_info = "neutral"
        if context and 'market_regime' in context.results:
            regime_result = context.results['market_regime']
            regime_type = regime_result.get('regime', 'RANGING')
            regime_confidence = regime_result.get('confidence', 0.5)
            
            if regime_type == 'HIGH_VOLATILITY':
                regime_adjustment = 1.3  # Wider trail in chaotic markets
                regime_info = f"high_volatility ({regime_confidence:.2f})"
            elif regime_type == 'RANGING':
                regime_adjustment = 0.8  # Tighter trail in ranging markets
                regime_info = f"ranging ({regime_confidence:.2f})"
            elif regime_type in ['TREND_UP', 'TREND_DOWN']:
                # In strong trends, use wider trail to avoid premature exits
                regime_adjustment = 1.15
                regime_info = f"trend ({regime_confidence:.2f})"
        
        # Adjust step based on Pattern strength (if context provided)
        pattern_adjustment = 1.0
        pattern_info = "none"
        if context and 'pattern_recognition' in context.results:
            pattern_result = context.results['pattern_recognition']
            patterns = pattern_result.get('patterns_detected', [])
            if patterns:
                # Strong reversal patterns suggest tighter trailing
                max_pattern_strength = max([p.get('strength', 0) for p in patterns])
                pattern_type = patterns[0].get('type', '')
                
                if 'reversal' in pattern_type.lower() or 'top' in pattern_type.lower() or 'bottom' in pattern_type.lower():
                    pattern_adjustment = 0.85  # Tighter for reversals
                    pattern_info = f"reversal pattern ({max_pattern_strength:.2f})"
                elif max_pattern_strength > 0.8:
                    pattern_adjustment = 0.9  # Slightly tighter for strong patterns
                    pattern_info = f"strong pattern ({max_pattern_strength:.2f})"
        
        # Calculate final step percentage
        step_pct = base_step_pct * regime_adjustment * pattern_adjustment
        step_pct = max(self.min_step_pct, step_pct)
        
        # Trail from highest price since entry
        trail_price = high_since_entry * (1 - step_pct / 100)
        
        return {
            'trail_price': trail_price,
            'step_pct': step_pct,
            'base_step_pct': base_step_pct,
            'profit_locked': (trail_price - entry_price) / entry_price * 100,
            'reasoning': {
                'atr_step': atr_step,
                'regime_adjustment': regime_info,
                'pattern_adjustment': pattern_info,
                'final_multiplier': regime_adjustment * pattern_adjustment
            }
        }
    
    def should_exit(self, current_price: float, trail_price: float, side: str = 'LONG') -> bool:
        """Check if price hit trailing stop"""
        if trail_price is None:
            return False
        
        if side == 'LONG':
            return current_price <= trail_price
        else:
            return current_price >= trail_price

