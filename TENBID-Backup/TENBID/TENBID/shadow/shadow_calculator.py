"""Shadow Calculator - parallel calculations for forbidden trades and hypothesis testing"""
import json
from datetime import datetime

class ShadowCalculator:
    def __init__(self, config, db):
        self.db = db
        self.enabled = config.getboolean('SHADOW', 'enabled')
        self.tests = config.get_list('SHADOW', 'tests')
    
    def analyze_forbidden_trade(self, signal_data):
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
            'timestamp': datetime.now().isoformat()
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

