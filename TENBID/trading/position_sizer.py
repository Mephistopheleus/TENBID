"""Dynamic Position Sizer - calculates position size based on confidence, volatility and data quality"""

from typing import Dict, Optional
from core.analysis_context import AnalysisContext


class PositionSizer:
    def __init__(self, config):
        self.min_pos_pct = config.getfloat('RISK', 'min_position_pct')
        self.max_pos_pct = config.getfloat('RISK', 'max_position_pct')
        self.min_sl_pct = config.getfloat('RISK', 'min_sl_pct')
        self.max_sl_pct = config.getfloat('RISK', 'max_sl_pct')
        self.target_rr = config.getfloat('RISK', 'target_rr_ratio')
    
    def calculate(self, confidence: float, context: AnalysisContext, current_price: float) -> Dict:
        """
        Calculate dynamic position size, SL, and TP using full analysis context.
        
        Args:
            confidence: Overall confidence score (0.5-1.0)
            context: AnalysisContext with all analyzer results and lineage
            current_price: Current market price
            
        Returns:
            Dictionary with position parameters and reasoning
        """
        
        # 1. Get ATR for volatility-based stops from the most reliable timeframe
        atr = 0
        atr_source = "unknown"
        
        # Prefer higher timeframes for more stable ATR
        for tf in ['1h', '4h', '15m', '5m']:
            if tf in context.synthetic_data:
                df = context.synthetic_data[tf]
                if 'atr' in df.columns:
                    atr = df['atr'].iloc[-1] if len(df) > 0 else 0
                    atr_source = tf
                    break
        
        if atr == 0 and '5m' in context.market_data:
            df = context.market_data['5m']
            if 'atr' in df.columns:
                atr = df['atr'].iloc[-1] if len(df) > 0 else 0
                atr_source = "5m"
        
        atr_pct = (atr / current_price * 100) if current_price > 0 and atr > 0 else 1.0
        
        # 2. Adjust SL based on Market Regime (if available)
        regime_penalty = 1.0
        regime_info = "neutral"
        if 'market_regime' in context.results:
            regime_result = context.results['market_regime']
            regime_type = regime_result.get('regime', 'RANGING')
            regime_confidence = regime_result.get('confidence', 0.5)
            
            if regime_type == 'HIGH_VOLATILITY':
                regime_penalty = 1.5  # Wider stop in chaotic markets
                regime_info = f"high_volatility ({regime_confidence:.2f})"
            elif regime_type == 'RANGING':
                regime_penalty = 0.8  # Tighter stop in ranging markets
                regime_info = f"ranging ({regime_confidence:.2f})"
            elif regime_type in ['TREND_UP', 'TREND_DOWN']:
                regime_penalty = 1.0  # Standard stop in trends
                regime_info = f"trend ({regime_confidence:.2f})"
        
        # 3. Adjust SL based on pattern strength (if patterns detected)
        pattern_bonus = 0.0
        pattern_info = "none"
        if 'pattern_recognition' in context.results:
            pattern_result = context.results['pattern_recognition']
            patterns = pattern_result.get('patterns_detected', [])
            if patterns:
                # Strong patterns allow tighter stops
                max_pattern_strength = max([p.get('strength', 0) for p in patterns])
                pattern_bonus = max_pattern_strength * 0.2  # Up to 20% tighter
                pattern_info = f"{len(patterns)} patterns (max_strength: {max_pattern_strength:.2f})"
        
        # Calculate stop loss percentage
        base_sl_pct = max(self.min_sl_pct, min(self.max_sl_pct, atr_pct * 1.5))
        adjusted_sl_pct = base_sl_pct * regime_penalty * (1.0 - pattern_bonus)
        adjusted_sl_pct = max(self.min_sl_pct, min(self.max_sl_pct, adjusted_sl_pct))
        
        # 4. Calculate position percentage based on confidence AND data quality
        confidence_factor = (confidence - 0.5) / 0.5  # Normalize 0.5-1.0 to 0-1
        
        # Factor in data quality from lineage
        data_quality_factor = 1.0
        quality_details = []
        for name, lineage in context.lineages.items():
            if hasattr(lineage, 'quality') and lineage.quality:
                q_score = lineage.quality.quality_score
                if q_score < 0.7:  # Penalize low quality data
                    data_quality_factor *= 0.8
                    quality_details.append(f"{name}: {q_score:.2f}")
        
        if quality_details:
            data_quality_factor = max(0.5, data_quality_factor)  # Cap penalty at 50%
        
        position_pct = self.min_pos_pct + (self.max_pos_pct - self.min_pos_pct) * confidence_factor * data_quality_factor
        position_pct = max(self.min_pos_pct, min(self.max_pos_pct, position_pct))
        
        # Calculate take profit based on R/R ratio
        tp_pct = adjusted_sl_pct * self.target_rr
        
        # Calculate actual prices
        sl_price = current_price * (1 - adjusted_sl_pct / 100)
        tp_price = current_price * (1 + tp_pct / 100)
        
        return {
            'position_pct': position_pct,
            'sl_pct': adjusted_sl_pct,
            'tp_pct': tp_pct,
            'sl_price': sl_price,
            'tp_price': tp_price,
            'rr_ratio': self.target_rr,
            'entry_price': current_price,
            'reasoning': {
                'atr_used': atr,
                'atr_source': atr_source,
                'atr_pct': atr_pct,
                'base_sl_pct': base_sl_pct,
                'regime_adjustment': regime_info,
                'pattern_adjustment': pattern_info,
                'data_quality_factor': data_quality_factor,
                'quality_details': quality_details if quality_details else ["all sources high quality"],
                'confidence_factor': confidence_factor
            }
        }

