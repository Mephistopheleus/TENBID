"""Market Analyzer - analyzes price action, trends, support/resistance"""
import pandas as pd
import numpy as np

class MarketAnalyzer:
    def __init__(self, config):
        pass
    
    def analyze(self, data_dict):
        """Analyze all timeframes and return signals"""
        analysis = {}
        
        for tf, df in data_dict.items():
            if len(df) < 2:
                continue
            
            # Basic metrics
            last_close = df['close'].iloc[-1]
            prev_close = df['close'].iloc[-2]
            change_pct = (last_close - prev_close) / prev_close * 100
            
            # Trend detection (simple MA crossover)
            if len(df) >= 20:
                ma_short = df['close'].rolling(9).mean().iloc[-1]
                ma_long = df['close'].rolling(21).mean().iloc[-1]
                trend = 1 if ma_short > ma_long else (-1 if ma_short < ma_long else 0)
            else:
                trend = 0
            
            # Support/Resistance levels (recent high/low)
            if len(df) >= 10:
                recent_high = df['high'].rolling(10).max().iloc[-1]
                recent_low = df['low'].rolling(10).min().iloc[-1]
                sr_strength = 0.9 if abs(last_close - recent_low) / last_close < 0.01 else 0.5
            else:
                recent_high = last_close
                recent_low = last_close
                sr_strength = 0.5
            
            # Volume analysis
            avg_volume = df['volume'].rolling(20).mean().iloc[-1] if len(df) >= 20 else df['volume'].iloc[-1]
            current_volume = df['volume'].iloc[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
            volume_score = min(1.0, volume_ratio / 2)
            
            analysis[tf] = {
                'price': last_close,
                'change_pct': change_pct,
                'trend': trend,
                'trend_strength': abs(trend),
                'support': recent_low,
                'resistance': recent_high,
                'sr_strength': sr_strength,
                'volume_score': volume_score,
                'atr': self._calculate_atr(df)
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

