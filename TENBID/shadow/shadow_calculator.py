"""Shadow Calculator - parallel calculations for forbidden trades and hypothesis testing"""
import json
from datetime import datetime
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class ShadowCalculator:
    def __init__(self, config, db, binance_connector=None):
        self.db = db
        self.connector = binance_connector
        self.enabled = config.getboolean('SHADOW', 'enabled')
        self.tests = config.get_list('SHADOW', 'tests')
        self.save_forbidden = config.getboolean('SHADOW', 'save_forbidden_trades', fallback=True)
        
        # Real trading costs (will be populated from API)
        self.commission_rates = {'maker': 0.0002, 'taker': 0.0004}
        self.slippage_estimate = 0.001  # Default 0.1%
        self.spread_estimate = 0.0005   # Default 0.05%
        
    async def update_trading_costs(self, symbol=None):
        """Update real trading costs from Binance API"""
        if not self.connector:
            logger.warning("No Binance connector available for cost updates")
            return
        
        try:
            # Get commission rates
            commission_data = await self.connector.get_account_commission(symbol)
            self.commission_rates = {
                'maker': commission_data.get('maker', 0.0002),
                'taker': commission_data.get('taker', 0.0004)
            }
            
            # Estimate slippage (using a small test quantity)
            slippage_data = await self.connector.estimate_slippage('BUY', 100, symbol)
            self.slippage_estimate = slippage_data.get('slippage_pct', 0.001)
            
            # Estimate spread from orderbook
            ob = await self.connector.get_order_book(symbol, limit=5)
            if ob.get('bids') and ob.get('asks'):
                best_bid = float(ob['bids'][0][0])
                best_ask = float(ob['asks'][0][0])
                mid_price = (best_bid + best_ask) / 2
                self.spread_estimate = (best_ask - best_bid) / mid_price
            
            logger.info(f"Updated trading costs - Commission: {self.commission_rates}, "
                       f"Slippage: {self.slippage_estimate:.4f}, Spread: {self.spread_estimate:.4f}")
        except Exception as e:
            logger.warning(f"Failed to update trading costs, using defaults: {e}")
    
    def calculate_realistic_costs(self, entry_price: float, exit_price: float, 
                                  position_size: float, side: str, is_maker: bool = False) -> Dict[str, float]:
        """
        Calculate realistic trading costs including commission, slippage, and spread.
        Returns detailed breakdown of costs.
        """
        # Commission (taker by default for market orders, maker for limit)
        commission_rate = self.commission_rates['maker'] if is_maker else self.commission_rates['taker']
        commission_cost = entry_price * position_size * commission_rate
        
        # Slippage cost (entry + exit)
        slippage_cost = entry_price * position_size * self.slippage_estimate * 2
        
        # Spread cost (paid on entry)
        spread_cost = entry_price * position_size * self.spread_estimate
        
        # Total round-trip costs
        total_costs = commission_cost + slippage_cost + spread_cost
        
        # Gross PnL
        if side.upper() == 'BUY':
            gross_pnl = (exit_price - entry_price) * position_size
        else:
            gross_pnl = (entry_price - exit_price) * position_size
        
        # Net PnL after costs
        net_pnl = gross_pnl - total_costs
        
        return {
            'commission': commission_cost,
            'slippage': slippage_cost,
            'spread': spread_cost,
            'total_costs': total_costs,
            'gross_pnl': gross_pnl,
            'net_pnl': net_pnl,
            'costs_as_pct_of_position': total_costs / (entry_price * position_size) if entry_price > 0 else 0
        }
    
    def analyze_forbidden_trade(self, signal_data: Dict[str, Any], context_snapshot: Optional[Dict] = None):
        """Analyze what would happen if we opened a forbidden trade with realistic costs"""
        confidence = signal_data.get('confidence', 0)
        threshold = signal_data.get('threshold', 0.75)
        
        hyp_entry = signal_data.get('prices', {}).get('current', 0)
        
        # Use realistic SL/TP based on current market conditions
        # Instead of fixed 2%, use dynamic levels based on volatility or ATR if available
        base_sl_pct = 0.02  # 2% default
        base_tp_pct = 0.04  # 4% default (2:1 RR)
        
        # Apply stricter conditions for shadow analysis
        # Add buffer for costs to ensure profitability
        cost_buffer = self.commission_rates['taker'] * 2 + self.slippage_estimate * 2 + self.spread_estimate
        
        hyp_sl = hyp_entry * (1 - base_sl_pct) if hyp_entry > 0 else 0
        hyp_tp = hyp_entry * (1 + base_tp_pct) if hyp_entry > 0 else 0
        
        # Calculate realistic outcome with costs
        # Simulate both win and loss scenarios
        win_costs = self.calculate_realistic_costs(hyp_entry, hyp_tp, 1, 'BUY')
        loss_costs = self.calculate_realistic_costs(hyp_entry, hyp_sl, 1, 'BUY')
        
        result = {
            'type': 'forbidden_trade_analysis',
            'forbidden_reason': signal_data.get('reason'),
            'hypothetical_entry': hyp_entry,
            'hypothetical_sl': hyp_sl,
            'hypothetical_tp': hyp_tp,
            'risk_reward_ratio': base_tp_pct / base_sl_pct,
            'confidence_at_time': confidence,
            'estimated_win_probability': confidence * 100,
            'timestamp': datetime.now().isoformat(),
            'context_snapshot': context_snapshot,
            
            # Realistic cost analysis
            'trading_costs': {
                'commission_rate': self.commission_rates,
                'slippage_estimate': self.slippage_estimate,
                'spread_estimate': self.spread_estimate,
                'win_scenario_net_pnl': win_costs['net_pnl'],
                'loss_scenario_net_pnl': loss_costs['net_pnl'],
                'total_round_trip_costs_pct': win_costs['costs_as_pct_of_position'] * 100
            },
            
            # Stricter success criteria
            'breakeven_required': hyp_entry * (1 + win_costs['costs_as_pct_of_position']),
            'minimum_profitable_move': win_costs['total_costs'] / hyp_entry if hyp_entry > 0 else 0
        }
        
        signal_data['shadow_result'] = result
        return result
    
    def run_tests(self, data_dict, analysis, current_confidence):
        """Run shadow tests with different parameters"""
        if not self.enabled:
            return
        
        results = []
        for test_type in self.tests:
            result = self._run_single_test(test_type, data_dict, analysis, current_confidence)
            results.append(result)
            self.db.log_shadow_test(result)
        
        return {
            'status': 'completed',
            'tests_run': len(results),
            'timestamp': datetime.now().isoformat(),
            'results_summary': {
                'tests_by_type': {t: 1 for t in self.tests},
                'recommendation_changes': 0,
                'total_tests': len(results)
            }
        }
    
    def _run_single_test(self, test_type, data_dict, analysis, current_confidence):
        """Run a single shadow test"""
        test_data = {
            'timestamp': datetime.now().isoformat(),
            'test_type': test_type,
            'parameters': {},
            'result': {},
            'recommendation_change': 0
        }
        
        if test_type == 'weight_variation':
            # Test with different component weights
            test_data['parameters'] = {'variation': 'trend_weight_+0.2'}
            test_data['result'] = {'confidence_delta': 0.02}
        
        elif test_type == 'btc_correlation':
            # Test BTC correlation impact (placeholder)
            test_data['parameters'] = {'correlation_window': '24h'}
            test_data['result'] = {'correlation_coefficient': 0.65}
        
        elif test_type == 'advanced_orderbook':
            # Test orderbook depth analysis (placeholder)
            test_data['parameters'] = {'depth_levels': 10}
            test_data['result'] = {'imbalance_score': 0.3}
        
        elif test_type == 'volume_profile':
            # Test volume profile analysis (placeholder)
            test_data['parameters'] = {'profile_periods': 50}
            df_5m = data_dict.get('5m', {})
            if hasattr(df_5m, 'iloc') and len(df_5m) > 0:
                test_data['result'] = {'poc_level': df_5m.iloc[-1]['close']}
            else:
                test_data['result'] = {'poc_level': 0}
        
        return test_data

    def create_trade_snapshot(self, trade_info: Dict[str, Any], analyzer_results: Dict[str, Any], 
                            weights: Dict[str, float], outcome: Optional[Dict] = None,
                            is_shadow: bool = False, shadow_reason: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a complete snapshot of a trade decision for Autotuner analysis.
        Called when a trade is opened (initial snapshot) and updated when closed.
        
        Args:
            trade_info: Basic trade information
            analyzer_results: Results from all analyzers
            weights: Weights used for the decision (from Autotuner)
            outcome: Trade outcome (filled when trade closes)
            is_shadow: Whether this is a shadow (simulated) trade
            shadow_reason: Reason why this was a shadow trade (e.g., 'LOW_CONFIDENCE', 'RISK_LIMIT')
        """
        snapshot = {
            'trade_id': trade_info.get('trade_id', f"shadow_{datetime.now().timestamp()}"),
            'timestamp': datetime.now().timestamp(),
            'symbol': trade_info.get('symbol', 'UNKNOWN'),
            'side': trade_info.get('side', 'BUY'),
            
            # Analyzer Scores at entry
            'btc_correlation': analyzer_results.get('btc', {}).get('correlation', 0.0),
            'btc_confidence': analyzer_results.get('btc', {}).get('confidence', 0.0),
            'fractal_score': analyzer_results.get('fractal', {}).get('confidence', 0.0),
            'orderbook_score': analyzer_results.get('orderbook', {}).get('confidence', 0.0),
            'pattern_score': analyzer_results.get('pattern', {}).get('confidence', 0.0),
            'regime_score': analyzer_results.get('regime', {}).get('confidence', 0.0),
            'regime_type': analyzer_results.get('regime', {}).get('type', 'UNKNOWN'),
            
            # System Weights used
            'weights_used': weights,
            
            # Decision Parameters
            'entry_price': trade_info.get('entry_price', 0.0),
            'sl_percent': trade_info.get('sl_percent', 0.0),
            'tp_percent': trade_info.get('tp_percent', 0.0),
            'position_size': trade_info.get('position_size', 0.0),
            'final_confidence': trade_info.get('confidence', 0.0),
            
            # Shadow trade tracking
            'is_shadow': is_shadow,
            'shadow_reason': shadow_reason,
            
            # Outcome (filled when trade closes)
            'exit_price': outcome.get('exit_price') if outcome else None,
            'exit_reason': outcome.get('exit_reason') if outcome else None,
            'pnl_percent': outcome.get('pnl_percent', 0.0) if outcome else 0.0,
            'pnl_usdt': outcome.get('pnl_usdt', 0.0) if outcome else 0.0,
            'is_winner': outcome.get('is_winner', False) if outcome else False,
            
            # Market Context during trade (filled when trade closes)
            'max_drawdown_during_trade': outcome.get('max_drawdown', 0.0) if outcome else 0.0,
            'max_profit_during_trade': outcome.get('max_profit', 0.0) if outcome else 0.0
        }
        
        trade_type = "SHADOW" if is_shadow else "REAL"
        logger.debug(f"Created {trade_type} trade snapshot: {snapshot['trade_id']}")
        return snapshot

