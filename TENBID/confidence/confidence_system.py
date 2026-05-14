"""Confidence System - calculates trade confidence with adaptive weights"""

class ConfidenceSystem:
    def __init__(self, config):
        self.base_threshold = config.getfloat('CONFIDENCE', 'base_confidence_threshold')
        self.adaptive_enabled = config.getboolean('CONFIDENCE', 'adaptive_threshold_enabled')
        self.min_threshold = config.getfloat('CONFIDENCE', 'min_threshold')
        self.max_threshold = config.getfloat('CONFIDENCE', 'max_threshold')
        self.volatility_factor = config.getfloat('CONFIDENCE', 'volatility_impact_factor')
        
        # Component weights (will be tuned by autotuner later)
        self.weights = {
            'trend': 1.0,
            'support_resistance': 1.2,
            'volume': 0.8,
            'pattern': 0.9,
            'orderbook': 1.5,
            'correlation': 1.1
        }
    
    def calculate(self, analysis, data_dict):
        """Calculate total confidence score from analysis"""
        scores = {}
        
        # Trend score (multi-timeframe agreement)
        trend_scores = [v['trend'] for v in analysis.values() if 'trend' in v]
        if trend_scores:
            avg_trend = sum(trend_scores) / len(trend_scores)
            scores['trend'] = (avg_trend + 1) / 2  # Normalize to 0-1
        else:
            scores['trend'] = 0.5
        
        # Support/Resistance score
        sr_scores = [v.get('sr_strength', 0.5) for v in analysis.values()]
        scores['support_resistance'] = max(sr_scores) if sr_scores else 0.5
        
        # Volume score
        vol_scores = [v.get('volume_score', 0.5) for v in analysis.values()]
        scores['volume'] = sum(vol_scores) / len(vol_scores) if vol_scores else 0.5
        
        # Pattern score (simplified - based on price action consistency)
        scores['pattern'] = 0.7  # Placeholder
        
        # Orderbook score (placeholder - will be enhanced)
        scores['orderbook'] = 0.6
        
        # Correlation score (placeholder)
        scores['correlation'] = 0.5
        
        # Calculate weighted average
        total_weight = sum(self.weights.values())
        weighted_sum = sum(scores[k] * self.weights.get(k, 1.0) for k in scores)
        total_confidence = weighted_sum / total_weight
        
        return {
            'total_confidence': total_confidence,
            'component_scores': scores,
            'weights_used': self.weights.copy()
        }
    
    def get_adaptive_threshold(self, analysis):
        """Calculate adaptive threshold based on market conditions"""
        if not self.adaptive_enabled:
            return self.base_threshold
        
        # Calculate average volatility (ATR normalized)
        atr_values = [v.get('atr', 0) for v in analysis.values() if 'atr' in v]
        avg_atr = sum(atr_values) / len(atr_values) if atr_values else 0
        
        # Get current price for normalization
        prices = [v.get('price', 1) for v in analysis.values() if 'price' in v]
        avg_price = sum(prices) / len(prices) if prices else 1
        
        # Normalized volatility
        norm_vol = avg_atr / avg_price if avg_price > 0 else 0
        
        # Adjust threshold: higher vol -> higher threshold
        adjustment = norm_vol * self.volatility_factor * 100
        adaptive_threshold = self.base_threshold + adjustment
        
        # Clamp to min/max
        return max(self.min_threshold, min(self.max_threshold, adaptive_threshold))

