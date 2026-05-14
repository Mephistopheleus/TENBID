"""Smart Trailing Stop - adaptive trailing based on market conditions"""

class SmartTrailing:
    def __init__(self, config):
        self.enabled = config.getboolean('TRAILING', 'enabled')
        self.activation_profit_pct = config.getfloat('TRAILING', 'activation_profit_pct')
        self.initial_step_pct = config.getfloat('TRAILING', 'initial_step_pct')
        self.atr_multiplier = config.getfloat('TRAILING', 'atr_multiplier')
        self.min_step_pct = config.getfloat('TRAILING', 'min_step_pct')
    
    def calculate_trail(self, entry_price, current_price, atr, high_since_entry):
        """Calculate trailing stop level"""
        if not self.enabled:
            return None
        
        # Check if activation profit reached
        profit_pct = (current_price - entry_price) / entry_price * 100
        if profit_pct < self.activation_profit_pct:
            return None
        
        # Dynamic step based on ATR
        atr_step = (atr / current_price * 100) * self.atr_multiplier if atr > 0 else self.initial_step_pct
        step_pct = max(self.min_step_pct, atr_step)
        
        # Trail from highest price since entry
        trail_price = high_since_entry * (1 - step_pct / 100)
        
        return {
            'trail_price': trail_price,
            'step_pct': step_pct,
            'profit_locked': (trail_price - entry_price) / entry_price * 100
        }
    
    def should_exit(self, current_price, trail_price, side='LONG'):
        """Check if price hit trailing stop"""
        if trail_price is None:
            return False
        
        if side == 'LONG':
            return current_price <= trail_price
        else:
            return current_price >= trail_price

