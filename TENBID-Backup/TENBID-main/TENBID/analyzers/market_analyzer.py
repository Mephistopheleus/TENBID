"""Market Analyzer - analyzes price action, trends, support/resistance"""
import pandas as pd
import numpy as np
from core.data_lineage import LineageTracker, DataSource, DataQuality, DataLineage

class MarketAnalyzer:
    def __init__(self, config):
        self.config = config
    
    def analyze(self, data_dict):
        """Analyze all timeframes and return analysis with lineage
        
        Args:
            data_dict: dict {timeframe: (df, lineage)}
            
        Returns:
            dict: {timeframe: analysis_dict} с маркировкой в 'lineage' ключе
        """
        analysis = {}
        
        for tf, (df, lineage) in data_dict.items():
            if len(df) < 2:
                continue
            
            # Basic metrics
            last_close = df['close'].iloc[-1]
            prev_close = df['close'].iloc[-2]
            change_pct = (last_close - prev_close) / prev_close * 100
            
            # Trend detection (simple MA crossover)
            trend_lineage = None
            if len(df) >= 20:
                ma_short = df['close'].rolling(9).mean().iloc[-1]
                ma_long = df['close'].rolling(21).mean().iloc[-1]
                trend = 1 if ma_short > ma_long else (-1 if ma_short < ma_long else 0)
                
                # Маркировка для расчета тренда
                trend_lineage = LineageTracker.create_calculated(
                    method="MA_crossover_9_21",
                    dependencies=[lineage],
                    quality=DataQuality.MEDIUM,
                    metadata={
                        'ma_short': ma_short,
                        'ma_long': ma_long,
                        'trend_direction': 'UP' if trend > 0 else ('DOWN' if trend < 0 else 'NEUTRAL')
                    }
                )
            else:
                trend = 0
            
            # Support/Resistance levels (recent high/low)
            sr_lineage = None
            if len(df) >= 10:
                recent_high = df['high'].rolling(10).max().iloc[-1]
                recent_low = df['low'].rolling(10).min().iloc[-1]
                sr_strength = 0.9 if abs(last_close - recent_low) / last_close < 0.01 else 0.5
                
                # Маркировка для S/R уровней
                sr_lineage = LineageTracker.create_calculated(
                    method="rolling_high_low_10",
                    dependencies=[lineage],
                    quality=DataQuality.MEDIUM,
                    metadata={
                        'recent_high': recent_high,
                        'recent_low': recent_low,
                        'distance_from_low': abs(last_close - recent_low) / last_close
                    }
                )
            else:
                recent_high = last_close
                recent_low = last_close
                sr_strength = 0.5
            
            # Volume analysis
            volume_lineage = None
            avg_volume = df['volume'].rolling(20).mean().iloc[-1] if len(df) >= 20 else df['volume'].iloc[-1]
            current_volume = df['volume'].iloc[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
            volume_score = min(1.0, volume_ratio / 2)
            
            # Маркировка для объема
            volume_lineage = LineageTracker.create_calculated(
                method="volume_ratio_20",
                dependencies=[lineage],
                quality=DataQuality.MEDIUM,
                metadata={
                    'current_volume': current_volume,
                    'avg_volume': avg_volume,
                    'volume_ratio': volume_ratio
                }
            )
            
            # ATR calculation
            atr_value = self._calculate_atr(df)
            atr_lineage = LineageTracker.create_calculated(
                method="ATR_14",
                dependencies=[lineage],
                quality=DataQuality.MEDIUM,
                metadata={'atr_value': atr_value}
            )
            
            # Объединяем все маркировки для этого ТФ
            merged_lineage = LineageTracker.merge_lineages(
                [l for l in [trend_lineage, sr_lineage, volume_lineage, atr_lineage] if l],
                method=f"market_analysis_{tf}"
            )
            
            analysis[tf] = {
                'price': last_close,
                'change_pct': change_pct,
                'trend': trend,
                'trend_strength': abs(trend),
                'support': recent_low,
                'resistance': recent_high,
                'sr_strength': sr_strength,
                'volume_score': volume_score,
                'atr': atr_value,
                'lineage': merged_lineage  # Добавляем маркировку
            }
        
        return analysis
    
    def _calculate_atr(self, df, period=14):
        """Calculate Average True Range"""
        if len(df) < period + 1:
            return 0.0
        
        high = df['high']
        low = df['low']
        close = df['close'].shift(1)
        
        tr1 = high - low
        tr2 = abs(high - close)
        tr3 = abs(low - close)
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]
        
        return atr if not pd.isna(atr) else 0.0

