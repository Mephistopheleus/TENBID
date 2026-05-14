"""Synthetic Timeframes Builder - builds higher TF from 5m base"""
import pandas as pd

class SyntheticTimeframes:
    def __init__(self, config):
        self.timeframes = config.get_list('DATA', 'synthetic_timeframes')
    
    def build_all(self, base_df):
        """Build all synthetic timeframes from base data"""
        result = {'5m': base_df}
        
        tf_map = {
            '10m': '10T', '15m': '15T', '30m': '30T',
            '1h': '60T', '4h': '240T', '12h': '720T'
        }
        
        for tf in self.timeframes:
            if tf in tf_map:
                rule = tf_map[tf]
                ohlc_dict = {
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum'
                }
                result[tf] = base_df.resample(rule).agg(ohlc_dict).dropna()
        
        return result

