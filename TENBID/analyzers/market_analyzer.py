"""Market Analyzer - analyzes price action, trends, support/resistance"""
import pandas as pd
import numpy as np
from core.data_lineage import DataLineageManager, LineageNode, LineageGraph, DataQuality, LineageTracker

class MarketAnalyzer:
    def __init__(self, config):
        self.config = config
    
    def analyze(self, data_dict):
        """Analyze all timeframes and return analysis with lineage + forecasts
        
        Args:
            data_dict: dict {timeframe: (df, lineage)}
            
        Returns:
            dict: {timeframe: analysis_dict} с маркировкой в 'lineage' ключе и прогнозами
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
            ma_short = None
            ma_long = None
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
            
            # === ГЕНЕРАЦИЯ ПРОГНОЗОВ ===
            forecasts = self._generate_forecasts(
                df, tf, last_close, trend, ma_short, ma_long,
                recent_high, recent_low, atr_value, volume_ratio, merged_lineage
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
                'lineage': merged_lineage,
                'forecasts': forecasts  # НОВОЕ: прогнозы
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
    
    def _generate_forecasts(self, df, timeframe, current_price, trend, ma_short, ma_long,
                           resistance, support, atr, volume_ratio, lineage):
        """
        Генерирует прогнозы на основе текущего анализа.
        
        Прогнозы строятся на разные горизонты с учётом:
        - Тренда (MA)
        - Уровней S/R
        - Волатильности (ATR)
        - Объёма
        
        Returns:
            list: Список прогнозов
        """
        forecasts = []
        
        if len(df) < 20 or ma_short is None or ma_long is None:
            return forecasts  # Недостаточно данных
        
        # Определяем временные параметры для ТФ
        tf_minutes = self._get_tf_minutes(timeframe)
        
        # Генерируем прогнозы на разные горизонты
        horizons = [1, 3, 5, 10]  # В свечах
        
        for horizon_candles in horizons:
            horizon_minutes = horizon_candles * tf_minutes
            
            # === ПРОГНОЗ НА ОСНОВЕ ТРЕНДА ===
            if trend != 0:
                # Расчёт целевой цены на основе тренда
                ma_distance = abs(ma_short - ma_long)
                trend_momentum = ma_distance / current_price
                
                # Прогнозируемое движение
                expected_move = current_price * trend_momentum * horizon_candles * 0.5
                price_target = current_price + (expected_move if trend > 0 else -expected_move)
                
                # Диапазон с учётом ATR
                price_min = price_target - (atr * horizon_candles * 0.5)
                price_max = price_target + (atr * horizon_candles * 0.5)
                
                # Уверенность зависит от силы тренда и объёма
                trend_strength = min(1.0, trend_momentum * 10)
                volume_factor = min(1.0, volume_ratio)
                confidence = (trend_strength * 0.7 + volume_factor * 0.3)
                
                # Сценарий
                scenario = "TREND_CONTINUATION_UP" if trend > 0 else "TREND_CONTINUATION_DOWN"
                
                # Факторы
                factors = ["ma_crossover"]
                if volume_ratio > 1.2:
                    factors.append("volume_increase")
                    confidence *= 1.1
                if trend_strength > 0.7:
                    factors.append("strong_momentum")
                
                confidence = min(1.0, confidence)
                
                # Создаём lineage для прогноза
                forecast_lineage = LineageTracker.create_calculated(
                    method=f"trend_forecast_{horizon_candles}c",
                    dependencies=[lineage],
                    quality=DataQuality.MEDIUM if confidence > 0.6 else DataQuality.LOW,
                    metadata={
                        'scenario': scenario,
                        'horizon_candles': horizon_candles,
                        'trend_momentum': trend_momentum
                    }
                )
                
                forecasts.append({
                    "timeframe": timeframe,
                    "horizon_candles": horizon_candles,
                    "horizon_minutes": horizon_minutes,
                    "scenario": scenario,
                    "price_target": round(price_target, 6),
                    "price_range": {
                        "min": round(price_min, 6),
                        "max": round(price_max, 6)
                    },
                    "confidence": round(confidence, 4),
                    "strength": round(trend_strength, 4),
                    "factors": factors,
                    "lineage": forecast_lineage
                })
            
            # === ПРОГНОЗ НА ОСНОВЕ S/R УРОВНЕЙ ===
            # Проверяем близость к уровням
            distance_to_resistance = abs(current_price - resistance) / current_price
            distance_to_support = abs(current_price - support) / current_price
            
            # Если близко к сопротивлению (< 1%)
            if distance_to_resistance < 0.01 and resistance > current_price:
                # Прогноз отскока или пробоя
                bounce_target = current_price - (atr * 2)
                breakout_target = resistance + (atr * 1.5)
                
                # Вероятность пробоя зависит от объёма и тренда
                breakout_probability = 0.3
                if volume_ratio > 1.5:
                    breakout_probability += 0.2
                if trend > 0:
                    breakout_probability += 0.2
                
                bounce_probability = 1.0 - breakout_probability
                
                # Прогноз пробоя
                if breakout_probability > 0.4:
                    forecast_lineage = LineageTracker.create_calculated(
                        method=f"resistance_breakout_forecast_{horizon_candles}c",
                        dependencies=[lineage],
                        quality=DataQuality.MEDIUM,
                        metadata={'resistance_level': resistance}
                    )
                    
                    forecasts.append({
                        "timeframe": timeframe,
                        "horizon_candles": horizon_candles,
                        "horizon_minutes": horizon_minutes,
                        "scenario": "BREAKOUT_UP",
                        "price_target": round(breakout_target, 6),
                        "price_range": {
                            "min": round(resistance, 6),
                            "max": round(breakout_target + atr, 6)
                        },
                        "confidence": round(breakout_probability, 4),
                        "strength": round(volume_ratio * 0.5, 4),
                        "factors": ["near_resistance", "volume_increase"] if volume_ratio > 1.5 else ["near_resistance"],
                        "lineage": forecast_lineage
                    })
                
                # Прогноз отскока
                if bounce_probability > 0.4:
                    forecast_lineage = LineageTracker.create_calculated(
                        method=f"resistance_bounce_forecast_{horizon_candles}c",
                        dependencies=[lineage],
                        quality=DataQuality.MEDIUM,
                        metadata={'resistance_level': resistance}
                    )
                    
                    forecasts.append({
                        "timeframe": timeframe,
                        "horizon_candles": horizon_candles,
                        "horizon_minutes": horizon_minutes,
                        "scenario": "resistance_bounce",
                        "price_target": round(bounce_target, 6),
                        "price_range": {
                            "min": round(bounce_target - atr, 6),
                            "max": round(current_price, 6)
                        },
                        "confidence": round(bounce_probability, 4),
                        "strength": 0.6,
                        "factors": ["near_resistance", "resistance_rejection"],
                        "lineage": forecast_lineage
                    })
            
            # Если близко к поддержке (< 1%)
            if distance_to_support < 0.01 and support < current_price:
                # Прогноз отскока или пробоя вниз
                bounce_target = current_price + (atr * 2)
                breakdown_target = support - (atr * 1.5)
                
                breakdown_probability = 0.3
                if volume_ratio > 1.5:
                    breakdown_probability += 0.2
                if trend < 0:
                    breakdown_probability += 0.2
                
                bounce_probability = 1.0 - breakdown_probability
                
                # Прогноз отскока вверх
                if bounce_probability > 0.4:
                    forecast_lineage = LineageTracker.create_calculated(
                        method=f"support_bounce_forecast_{horizon_candles}c",
                        dependencies=[lineage],
                        quality=DataQuality.MEDIUM,
                        metadata={'support_level': support}
                    )
                    
                    forecasts.append({
                        "timeframe": timeframe,
                        "horizon_candles": horizon_candles,
                        "horizon_minutes": horizon_minutes,
                        "scenario": "support_bounce",
                        "price_target": round(bounce_target, 6),
                        "price_range": {
                            "min": round(current_price, 6),
                            "max": round(bounce_target + atr, 6)
                        },
                        "confidence": round(bounce_probability, 4),
                        "strength": 0.7,
                        "factors": ["near_support", "support_hold"],
                        "lineage": forecast_lineage
                    })
        
        return forecasts
    
    def _get_tf_minutes(self, timeframe):
        """Конвертирует таймфрейм в минуты"""
        tf_map = {
            '1m': 1, '3m': 3, '5m': 5, '10m': 10, '15m': 15, '30m': 30,
            '1h': 60, '2h': 120, '4h': 240, '6h': 360, '12h': 720, '1d': 1440
        }
        return tf_map.get(timeframe, 5)  # По умолчанию 5 минут
