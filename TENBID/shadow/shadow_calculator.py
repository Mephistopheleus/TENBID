"""
Shadow Calculator - parallel calculations for forbidden trades and hypothesis testing
Full cycle tracking: creates snapshots, tracks outcomes of forbidden trades
"""
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import logging
import asyncio

logger = logging.getLogger(__name__)

class ShadowCalculator:
    def __init__(self, config, db, binance_connector=None):
        self.db = db
        self.connector = binance_connector
        self.enabled = config.getboolean('SHADOW', 'enabled')
        self.tests = config.get_list('SHADOW', 'tests')
        self.save_forbidden = config.getboolean('SHADOW', 'save_forbidden_trades', fallback=True)
        
        # Tracking forbidden trades for delayed outcome analysis
        self.pending_forbidden_trades = {}  # signal_id -> trade_data
        self.outcome_check_delay = config.getint('SHADOW', 'outcome_check_delay', fallback=1)  # candles (reduced for faster learning)
        
        # Persist pending trades to DB to survive restarts
        self.persist_pending = config.getboolean('SHADOW', 'persist_pending', fallback=True)
        
        # Real trading costs (will be populated from API)
        self.commission_rates = {'maker': 0.0002, 'taker': 0.0004}
        self.slippage_estimate = 0.001  # Default 0.1%
        self.spread_estimate = 0.0005   # Default 0.05%
        
        # Weak factors tracking for Shadow Lab
        self.weak_factors_buffer = []  # Factors with confidence < 0.25 for lab analysis
        
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


    def create_forbidden_snapshot(self, signal_data: Dict[str, Any], analyzer_results: Dict[str, Any],
                                  weights: Dict[str, float], context_snapshot: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Create a complete snapshot for a FORBIDDEN trade (HOLD decision).
        This snapshot will be tracked and checked later for outcome.
        
        Args:
            signal_data: Signal data with confidence, threshold, prices
            analyzer_results: Results from all analyzers
            weights: Weights used for the decision (from Autotuner)
            context_snapshot: Context at the time of decision
        
        Returns:
            Snapshot dict ready for tracking and future outcome analysis
        """
        hyp_entry = signal_data.get('prices', {}).get('current', 0)
        base_sl_pct = 0.02  # 2% default
        base_tp_pct = 0.04  # 4% default (2:1 RR)
        
        snapshot = {
            'trade_id': f"forbidden_{datetime.now().timestamp()}",
            'timestamp': datetime.now().timestamp(),
            'symbol': signal_data.get('symbol', 'UNKNOWN'),
            'side': signal_data.get('side', 'BUY'),
            
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
            'entry_price': hyp_entry,
            'sl_percent': base_sl_pct,
            'tp_percent': base_tp_pct,
            'position_size': signal_data.get('position', {}).get('position_size', 0.0),
            'final_confidence': signal_data.get('confidence', 0.0),
            
            # Shadow trade tracking
            'is_shadow': True,
            'shadow_reason': signal_data.get('reason', 'LOW_CONFIDENCE'),
            
            # Outcome placeholders (to be filled later)
            'exit_price': None,
            'exit_reason': None,
            'pnl_percent': 0.0,
            'pnl_usdt': 0.0,
            'is_winner': False,
            
            # Market Context during trade (to be filled later)
            'max_drawdown_during_trade': 0.0,
            'max_profit_during_trade': 0.0,
            
            # Tracking metadata
            'candles_to_check': self.outcome_check_delay,
            'status': 'PENDING_OUTCOME',
            'context_at_entry': context_snapshot
        }
        
        # Extract weak factors for Shadow Lab
        weak_factors = {}
        for factor_name in ['btc_correlation', 'fractal_score', 'orderbook_score', 'pattern_score', 'regime_score']:
            factor_value = snapshot.get(factor_name, 0.0)
            if 0.05 < abs(factor_value) < 0.25:
                weak_factors[factor_name] = factor_value
        
        if weak_factors:
            snapshot['weak_factors'] = weak_factors
            self.weak_factors_buffer.append({
                'timestamp': datetime.now().isoformat(),
                'trade_id': snapshot['trade_id'],
                'weak_factors': weak_factors,
                'total_confidence': snapshot['final_confidence']
            })
        
        logger.info(f"Created forbidden trade snapshot: {snapshot['trade_id']} (confidence: {snapshot['final_confidence']:.3f})")
        return snapshot

    async def check_forbidden_outcomes(self, current_price: float, symbol: str, candle_data: Optional[Dict] = None):
        """
        Check outcomes of pending forbidden trades after N candles.
        Simulates what would have happened if we entered the trade.
        
        Args:
            current_price: Current market price
            symbol: Trading pair symbol
            candle_data: Dict with latest candle data {high, low, close, open} for realistic simulation
        
        Returns:
            List of completed forbidden trade snapshots with outcomes
        """
        completed_trades = []
        trades_to_remove = []
        
        for trade_id, trade_data in self.pending_forbidden_trades.items():
            # Decrement candle counter
            trade_data['candles_to_check'] -= 1
            
            # Get candle range for realistic simulation
            candle_high = candle_data.get('high', current_price) if candle_data else current_price
            candle_low = candle_data.get('low', current_price) if candle_data else current_price
            
            # Check if enough candles have passed (horizon reached)
            if trade_data['candles_to_check'] <= 0:
                entry = trade_data['entry_price']
                sl_pct = trade_data['sl_percent']
                tp_pct = trade_data['tp_percent']
                side = trade_data['side'].upper()
                
                # Calculate SL and TP levels
                if side == 'BUY':
                    sl_level = entry * (1 - sl_pct / 100)
                    tp_level = entry * (1 + tp_pct / 100)
                    
                    # REALISTIC SIMULATION: Check if price touched SL or TP during candle
                    # Priority: SL first (risk management), then TP
                    if candle_low <= sl_level:
                        # Hit Stop Loss - trade closed at SL
                        trade_data['exit_price'] = sl_level
                        trade_data['exit_reason'] = 'SL'
                        trade_data['pnl_percent'] = -sl_pct
                        trade_data['is_winner'] = False
                        trade_data['max_drawdown_during_trade'] = -sl_pct
                        logger.info(f"Forbidden {trade_id}: SL HIT at {sl_level:.6f} (low: {candle_low:.6f})")
                        
                    elif candle_high >= tp_level:
                        # Hit Take Profit - trade closed at TP
                        trade_data['exit_price'] = tp_level
                        trade_data['exit_reason'] = 'TP'
                        trade_data['pnl_percent'] = tp_pct
                        trade_data['is_winner'] = True
                        trade_data['max_profit_during_trade'] = tp_pct
                        logger.info(f"Forbidden {trade_id}: TP HIT at {tp_level:.6f} (high: {candle_high:.6f})")
                        
                    else:
                        # No SL/TP hit - close at current price (simulation end)
                        exit_price = current_price
                        trade_data['exit_price'] = exit_price
                        trade_data['exit_reason'] = 'HORIZON_END'
                        trade_data['pnl_percent'] = ((exit_price - entry) / entry) * 100
                        trade_data['is_winner'] = exit_price > entry
                        
                        # Track max excursion during trade
                        if candle_high > entry:
                            trade_data['max_profit_during_trade'] = ((candle_high - entry) / entry) * 100
                        if candle_low < entry:
                            trade_data['max_drawdown_during_trade'] = -((entry - candle_low) / entry) * 100
                            
                        logger.info(f"Forbidden {trade_id}: HORIZON END at {exit_price:.6f} | PnL: {trade_data['pnl_percent']:.2f}%")
                
                else:  # SELL
                    sl_level = entry * (1 + sl_pct / 100)
                    tp_level = entry * (1 - tp_pct / 100)
                    
                    if candle_high >= sl_level:
                        trade_data['exit_price'] = sl_level
                        trade_data['exit_reason'] = 'SL'
                        trade_data['pnl_percent'] = -sl_pct
                        trade_data['is_winner'] = False
                        trade_data['max_drawdown_during_trade'] = -sl_pct
                        logger.info(f"Forbidden {trade_id}: SL HIT at {sl_level:.6f} (high: {candle_high:.6f})")
                        
                    elif candle_low <= tp_level:
                        trade_data['exit_price'] = tp_level
                        trade_data['exit_reason'] = 'TP'
                        trade_data['pnl_percent'] = tp_pct
                        trade_data['is_winner'] = True
                        trade_data['max_profit_during_trade'] = tp_pct
                        logger.info(f"Forbidden {trade_id}: TP HIT at {tp_level:.6f} (low: {candle_low:.6f})")
                        
                    else:
                        exit_price = current_price
                        trade_data['exit_price'] = exit_price
                        trade_data['exit_reason'] = 'HORIZON_END'
                        trade_data['pnl_percent'] = ((entry - exit_price) / entry) * 100
                        trade_data['is_winner'] = exit_price < entry
                        
                        if candle_low < entry:
                            trade_data['max_profit_during_trade'] = ((entry - candle_low) / entry) * 100
                        if candle_high > entry:
                            trade_data['max_drawdown_during_trade'] = -((candle_high - entry) / entry) * 100
                            
                        logger.info(f"Forbidden {trade_id}: HORIZON END at {exit_price:.6f} | PnL: {trade_data['pnl_percent']:.2f}%")
                
                # Calculate realistic costs (commission, slippage, spread)
                cost_analysis = self.calculate_realistic_costs(
                    entry, 
                    trade_data['exit_price'] or current_price,
                    trade_data['position_size'] or 1, 
                    side
                )
                # Adjust PnL by costs
                trade_data['pnl_percent'] -= cost_analysis['costs_as_pct_of_position'] * 100
                trade_data['trading_costs'] = cost_analysis
                
                trade_data['status'] = 'COMPLETED'
                completed_trades.append(trade_data)
                trades_to_remove.append(trade_id)
        
        # Remove completed trades from pending
        for trade_id in trades_to_remove:
            del self.pending_forbidden_trades[trade_id]
        
        return completed_trades

    def register_forbidden_trade(self, snapshot: Dict[str, Any]):
        """
        Register a forbidden trade for delayed outcome checking.
        Also persists to database if enabled.
        
        Args:
            snapshot: Trade snapshot from create_forbidden_snapshot()
        """
        self.pending_forbidden_trades[snapshot['trade_id']] = snapshot
        
        # Persist to database for crash recovery
        if self.persist_pending:
            try:
                self.db.log_shadow_test({
                    'timestamp': datetime.now().isoformat(),
                    'test_type': 'forbidden_trade',
                    'parameters': {
                        'entry_price': snapshot['entry_price'],
                        'side': snapshot['side'],
                        'confidence': snapshot['final_confidence'],
                        'shadow_reason': snapshot['shadow_reason']
                    },
                    'result': {'status': 'PENDING'},
                    'recommendation_change': 0
                })
            except Exception as e:
                logger.warning(f"Failed to persist forbidden trade to DB: {e}")
        
        logger.info(f"Registered forbidden trade for tracking: {snapshot['trade_id']} (confidence: {snapshot['final_confidence']:.3f})")

    def get_weak_factors_for_lab(self) -> List[Dict]:
        """
        Get weak factors data for Shadow Lab analysis.
        
        Returns:
            List of weak factor observations for hypothesis generation
        """
        if not self.weak_factors_buffer:
            return []
        
        data = self.weak_factors_buffer.copy()
        self.weak_factors_buffer.clear()
        return data

