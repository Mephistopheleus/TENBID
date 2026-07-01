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
import logging
from typing import Dict, List, Any, Optional
from core.data_lineage import DataLineageManager

logger = logging.getLogger(__name__)


class MarketAnalyzer:
    """
    Основной анализатор рынка.
    Рассчитывает тренд, волатильность и объем для различных таймфреймов.
    Интегрирован с DataLineageManager v2.0.
    """

    def __init__(self, lineage_manager: DataLineageManager):
        if lineage_manager is None:
            raise ValueError("lineage_manager cannot be None")
        self.lineage_manager = lineage_manager
        self.logger = logging.getLogger(__name__)

    # --- Математические утилиты (Сохранены полностью) ---

    def _calculate_sma(self, data: List[float], period: int) -> Optional[float]:
        if len(data) < period:
            return None
        return sum(data[-period:]) / period

    def _calculate_ema(self, data: List[float], period: int) -> Optional[float]:
        if len(data) < period:
            return None
        multiplier = 2 / (period + 1)
        ema = sum(data[:period]) / period
        for price in data[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        return ema

    def _calculate_atr(self, highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
        if len(highs) < period + 1:
            return None
        
        tr_values = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            tr_values.append(tr)
        
        # Простое среднее для первых значений или экспоненциальное
        atr = sum(tr_values[:period]) / period
        for tr in tr_values[period:]:
            atr = (atr * (period - 1) + tr) / period
        
        return atr

    def _calculate_volume_ratio(self, current_volume: float, avg_volume: float) -> float:
        if avg_volume == 0:
            return 1.0
        return current_volume / avg_volume

    def _determine_trend_direction(self, sma_short: float, sma_long: float, price: float) -> str:
        if sma_short > sma_long and price > sma_short:
            return "BULLISH"
        elif sma_short < sma_long and price < sma_short:
            return "BEARISH"
        else:
            return "NEUTRAL"

    def _calculate_momentum(self, closes: List[float], period: int = 10) -> Optional[float]:
        if len(closes) < period + 1:
            return None
        return closes[-1] - closes[-period-1]

    # --- Основной метод анализа ---

    def analyze(self, market_data: Dict[str, Any], snapshot_id: str, context_profile_id: str) -> Dict[str, Any]:
        """
        Выполняет комплексный анализ рынка по всем таймфреймам.
        Создает узлы линейности для каждого компонента.
        
        :param market_data: Словарь вида {'5m': {...}, '1h': {...}, ...}
        :param snapshot_id: ID корневого снимка рынка.
        :param context_profile_id: Идентификатор контекста (напр., 'BTCUSDT').
        :return: Словарь с результатами анализа и ID созданных узлов.
        """
        results = {
            'context_profile_id': context_profile_id,
            'snapshot_id': snapshot_id,
            'timeframes': {},
            'lineage_nodes': [],  # Список ID всех созданных узлов
            'summary': {}
        }

        timeframes = market_data.keys()
        
        for tf in timeframes:
            tf_data = market_data[tf]
            closes = tf_data.get('closes', [])
            highs = tf_data.get('highs', [])
            lows = tf_data.get('lows', [])
            volumes = tf_data.get('volumes', [])
            
            # Trend detection (simple MA crossover)
            trend_lineage = None
            ma_short = None
            ma_long = None
            if len(df) >= 20:
                ma_short = df['close'].rolling(9).mean().iloc[-1]
                ma_long = df['close'].rolling(21).mean().iloc[-1]
                trend = 1 if ma_short > ma_long else (-1 if ma_short < ma_long else 0)
            if not closes or len(closes) < 20:
                self.logger.warning(f"Insufficient data for timeframe {tf}")
                continue

            try:
                # 1. Расчет индикаторов
                sma_short = self._calculate_sma(closes, 9)
                sma_long = self._calculate_sma(closes, 21)
                ema_fast = self._calculate_ema(closes, 12)
                ema_slow = self._calculate_ema(closes, 26)
                atr = self._calculate_atr(highs, lows, closes)
                
                current_price = closes[-1]
                current_volume = volumes[-1] if volumes else 0
                avg_volume = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else current_volume
                
                vol_ratio = self._calculate_volume_ratio(current_volume, avg_volume)
                trend_dir = self._determine_trend_direction(sma_short or 0, sma_long or 0, current_price)
                momentum = self._calculate_momentum(closes)

                # Нормализация уверенности для тренда (0..1)
                trend_confidence = 0.5
                if trend_dir == "BULLISH":
                    trend_confidence = min(1.0, (sma_short - sma_long) / (sma_long * 0.01) + 0.5) if sma_long else 0.5
                elif trend_dir == "BEARISH":
                    trend_confidence = min(1.0, (sma_long - sma_short) / (sma_short * 0.01) + 0.5) if sma_short else 0.5
                
                # 2. Создание узлов линейности (Lineage Nodes)
                
                # Узел Тренда
                trend_vector = {
                    'direction': trend_dir,
                    'sma_short': sma_short,
                    'sma_long': sma_long,
                    'momentum': momentum,
                    'price': current_price
                }
                try:
                    trend_node_id = self.lineage_manager.create_analysis_node(
                        parent_snapshot_id=snapshot_id,
                        analyzer_name=f"trend_{tf}",
                        result_vector=trend_vector,
                        confidence=trend_confidence,
                        additional_meta={'timeframe': tf, 'type': 'trend'}
                    )
                    results['lineage_nodes'].append(trend_node_id)
                except Exception as e:
                    self.logger.error(f"Failed to create trend node for {tf}: {e}")
                    trend_node_id = None

                # Узел Волатильности (ATR)
                vol_confidence = 0.8 if atr else 0.1
                volatility_vector = {
                    'atr': atr,
                    'atr_percent': (atr / current_price * 100) if atr and current_price else 0
                }
                try:
                    vol_node_id = self.lineage_manager.create_analysis_node(
                        parent_snapshot_id=snapshot_id,
                        analyzer_name=f"volatility_{tf}",
                        result_vector=volatility_vector,
                        confidence=vol_confidence,
                        additional_meta={'timeframe': tf, 'type': 'volatility'}
                    )
                    results['lineage_nodes'].append(vol_node_id)
                except Exception as e:
                    self.logger.error(f"Failed to create volatility node for {tf}: {e}")
                    vol_node_id = None

                # Узел Объема
                volume_confidence = min(1.0, vol_ratio / 2.0) # Пример эвристики
                volume_vector = {
                    'current_volume': current_volume,
                    'avg_volume': avg_volume,
                    'ratio': vol_ratio
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
                try:
                    vol_node_id = self.lineage_manager.create_analysis_node(
                        parent_snapshot_id=snapshot_id,
                        analyzer_name=f"volume_{tf}",
                        result_vector=volume_vector,
                        confidence=volume_confidence,
                        additional_meta={'timeframe': tf, 'type': 'volume'}
                    )
                    results['lineage_nodes'].append(vol_node_id)
                except Exception as e:
                    self.logger.error(f"Failed to create volume node for {tf}: {e}")

                # Сохранение результатов по TF
                results['timeframes'][tf] = {
                    'trend': trend_dir,
                    'trend_confidence': trend_confidence,
                    'atr': atr,
                    'volume_ratio': vol_ratio,
                    'momentum': momentum,
                    'nodes_count': len([n for n in results['lineage_nodes'] if tf in str(n)]) # Грубая оценка
                }

            except Exception as e:
                self.logger.error(f"Critical error analyzing timeframe {tf}: {e}")
                continue

        # Итоговое резюме
        bullish_count = sum(1 for tf in results['timeframes'].values() if tf['trend'] == 'BULLISH')
        bearish_count = sum(1 for tf in results['timeframes'].values() if tf['trend'] == 'BEARISH')
        
        if bullish_count > bearish_count:
            results['summary']['overall_trend'] = 'BULLISH'
        elif bearish_count > bullish_count:
            results['summary']['overall_trend'] = 'BEARISH'
        else:
            results['summary']['overall_trend'] = 'NEUTRAL'
            
        results['summary']['timeframes_analyzed'] = len(results['timeframes'])
        results['summary']['total_nodes_created'] = len(results['lineage_nodes'])

        return results

