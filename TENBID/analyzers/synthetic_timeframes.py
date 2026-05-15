"""Synthetic Timeframes Builder - builds higher TF from 5m base"""
import pandas as pd
from core.data_lineage import LineageTracker, DataSource, DataQuality, DataLineage

class SyntheticTimeframes:
    def __init__(self, config):
        self.timeframes = config.get_list('DATA', 'synthetic_timeframes')
    
    def build_all(self, base_df, base_lineage: DataLineage):
        """Build all synthetic timeframes from base data
        
        Args:
            base_df: Базовый DataFrame с 5m свечами
            base_lineage: Маркировка базовых данных
            
        Returns:
            dict: Словарь {timeframe: (df, lineage)}
        """
        result = {'5m': (base_df, base_lineage)}
        
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
                synthetic_df = base_df.resample(rule).agg(ohlc_dict).dropna()
                
                # Создаем маркировку для синтетического ТФ
                synthetic_lineage = LineageTracker.create_calculated(
                    method=f"resample_{rule}",
                    dependencies=[base_lineage],
                    quality=DataQuality.MEDIUM,  # Синтетические данные имеют среднее качество
                    metadata={
                        'source_tf': '5m',
                        'target_tf': tf,
                        'candles_count': len(synthetic_df)
                    }
                )
                
                result[tf] = (synthetic_df, synthetic_lineage)
        
        return result

