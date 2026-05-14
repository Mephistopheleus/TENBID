"""Dynamic Position Sizer - calculates position size based on confidence and volatility"""

class PositionSizer:
    def __init__(self, config):
        self.min_pos_pct = config.getfloat('RISK', 'min_position_pct')
        self.max_pos_pct = config.getfloat('RISK', 'max_position_pct')
        self.min_sl_pct = config.getfloat('RISK', 'min_sl_pct')
        self.max_sl_pct = config.getfloat('RISK', 'max_sl_pct')
        self.target_rr = config.getfloat('RISK', 'target_rr_ratio')
    
    def calculate(self, confidence, analysis, current_price):
        """Calculate dynamic position size, SL, and TP"""
        
        # Get ATR for volatility-based stops
        atr = analysis.get('5m', {}).get('atr', 0)
        atr_pct = (atr / current_price * 100) if current_price > 0 and atr > 0 else 1.0
        
        # Calculate stop loss percentage based on ATR
        # Higher volatility -> wider stop
        sl_pct = max(
            self.min_sl_pct,
            min(self.max_sl_pct, atr_pct * 1.5)
        )
        
        # Calculate position percentage based on confidence
        # Higher confidence -> larger position
        confidence_factor = (confidence - 0.5) / 0.5  # Normalize 0.5-1.0 to 0-1
        position_pct = self.min_pos_pct + (self.max_pos_pct - self.min_pos_pct) * confidence_factor
        position_pct = max(self.min_pos_pct, min(self.max_pos_pct, position_pct))
        
        # Calculate take profit based on R/R ratio
        tp_pct = sl_pct * self.target_rr
        
        # Calculate actual prices
        sl_price = current_price * (1 - sl_pct / 100)
        tp_price = current_price * (1 + tp_pct / 100)
        
        return {
            'position_pct': position_pct,
            'sl_pct': sl_pct,
            'tp_pct': tp_pct,
            'sl_price': sl_price,
            'tp_price': tp_price,
            'rr_ratio': self.target_rr,
            'entry_price': current_price
        }

