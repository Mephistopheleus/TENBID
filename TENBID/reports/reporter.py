"""Reporter - generates comprehensive trading reports"""
from datetime import datetime

class Reporter:
    def __init__(self, db, config):
        self.db = db
        self.config = config
        self.initial_balance = config.getfloat('GENERAL', 'initial_balance')
        self.current_balance = self.initial_balance
    
    def generate_report(self):
        """Generate comprehensive report"""
        stats = self.db.get_statistics()
        
        # Calculate metrics
        total_signals = stats['total_signals']
        open_decisions = stats['decisions'].get('OPEN', 0)
        hold_decisions = stats['decisions'].get('HOLD', 0)
        
        total_trades = stats['trades']['total']
        winning_trades = stats['trades']['winning']
        losing_trades = stats['trades']['losing']
        
        # Winrate
        winrate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # Shadow winrate (from forbidden trades analysis)
        shadow_wr = self._calculate_shadow_winrate()
        
        # PnL
        total_pnl = stats['trades']['total_pnl']
        pnl_pct = (total_pnl / self.initial_balance * 100) if self.initial_balance > 0 else 0
        
        # Projected monthly PnL (simplified)
        projected_monthly = pnl_pct * (30 * 24 * 2)  # Assuming 30-sec cycles
        
        # Current balance
        self.current_balance = self.initial_balance + total_pnl
        
        return {
            'Balance': f"{self.current_balance:.2f} USDT (Start: {self.initial_balance:.2f})",
            'PnL': f"{total_pnl:.2f} USDT ({pnl_pct:.2f}%)",
            'Projected Monthly PnL': f"{projected_monthly:.1f}%",
            'Total Signals': total_signals,
            'Open Decisions': open_decisions,
            'Hold Decisions': hold_decisions,
            'Total Trades': total_trades,
            'Winning Trades': winning_trades,
            'Losing Trades': losing_trades,
            'Winrate': f"{winrate:.1f}%",
            'Shadow Winrate': f"{shadow_wr:.1f}%",
            'Avg Trade PnL': f"{stats['trades']['avg_pnl_pct']:.2f}%" if total_trades > 0 else "N/A"
        }
    
    def _calculate_shadow_winrate(self):
        """Calculate winrate from shadow/forbidden trade analysis"""
        signals = self.db.get_all_signals()
        if not signals:
            return 0.0
        
        shadow_wins = 0
        shadow_total = 0
        
        for signal in signals:
            if signal.get('decision') == 'HOLD' and signal.get('shadow_result_json'):
                import json
                try:
                    shadow = json.loads(signal['shadow_result_json'])
                    conf = shadow.get('estimated_win_probability', 0)
                    if conf > 50:
                        shadow_wins += 1
                    shadow_total += 1
                except:
                    pass
        
        return (shadow_wins / shadow_total * 100) if shadow_total > 0 else 0.0

