"""Shadow Calculator - parallel calculations for forbidden trades and hypothesis testing"""
import json
from datetime import datetime
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class ShadowCalculator:
    def __init__(self, config, db):
        self.db = db
        self.enabled = config.getboolean('SHADOW', 'enabled')
        self.tests = config.get_list('SHADOW', 'tests')
        
    def analyze_forbidden_trade(self, signal_data: Dict[str, Any], context_snapshot: Optional[Dict] = None):
        """Analyze what would happen if we opened a forbidden trade"""
        confidence = signal_data.get('confidence', 0)
        threshold = signal_data.get('threshold', 0.75)
        
        # Calculate hypothetical R/R and win probability
        hyp_entry = signal_data.get('prices', {}).get('current', 0)
        hyp_sl = hyp_entry * 0.98 if hyp_entry > 0 else 0
        hyp_tp = hyp_entry * 1.02 if hyp_entry > 0 else 0
        
        result = {
            'type': 'forbidden_trade_analysis',
            'forbidden_reason': signal_data.get('reason'),
            'hypothetical_entry': hyp_entry,
            'hypothetical_sl': hyp_sl,
            'hypothetical_tp': hyp_tp,
            'risk_reward_ratio': 2.0,
            'confidence_at_time': confidence,
            'estimated_win_probability': confidence * 100,
            'timestamp': datetime.now().isoformat(),
            'context_snapshot': context_snapshot  # Store full context for Autotuner
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
            test_data['result'] = {'poc_level': data_dict.get('5m', {}).iloc[-1]['close'] if len(data_dict.get('5m', [])) > 0 else 0}
        
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
            'fractal_score': analyzer_results.get('fractal', {}).get('score', 0.0),
            'orderbook_score': analyzer_results.get('orderbook', {}).get('score', 0.0),
            'pattern_score': analyzer_results.get('pattern', {}).get('score', 0.0),
            'regime_score': analyzer_results.get('regime', {}).get('score', 0.0),
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

