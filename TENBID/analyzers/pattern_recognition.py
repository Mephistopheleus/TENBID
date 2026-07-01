"""
Pattern Recognition Analyzer
Анализирует свечные паттерны (микро) и графические фигуры (макро).
Возвращает сигнал и уровень уверенности на основе найденных фигур.
Поддерживает мульти-ТФ анализ.
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
from core.data_lineage import DataLineageManager, LineageNode, LineageGraph, DataLineage, DataSource, DataQuality, LineageTracker
from .multi_tf_context import MultiTFContextAggregator, TimeframeResult

class PatternRecognitionAnalyzer:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.aggregator = MultiTFContextAggregator()
        self.lineage = None
        
    def analyze(self, context) -> Dict[str, Any]:
import logging
from typing import Dict, List, Any, Optional
from core.data_lineage import DataLineageManager

logger = logging.getLogger(__name__)

class PatternAnalyzer:
    """
    Анализатор свечных паттернов.
    Распознает классические формации (Doji, Hammer, Engulfing и т.д.)
    и регистрирует их в графе данных через DataLineageManager.
    """

    # Веса паттернов (сила сигнала от -1.0 до 1.0)
    PATTERN_WEIGHTS = {
        'doji': 0.1,
        'hammer': 0.6,
        'inverted_hammer': 0.5,
        'hanging_man': -0.5,
        'shooting_star': -0.6,
        'bullish_engulfing': 0.8,
        'bearish_engulfing': -0.8,
        'morning_star': 0.9,
        'evening_star': -0.9,
        'piercing_line': 0.7,
        'dark_cloud_cover': -0.7,
        'three_white_soldiers': 0.9,
        'three_black_crows': -0.9
    }

    def __init__(self, lineage_manager: DataLineageManager, min_confidence: float = 0.4):
        """
        :param lineage_manager: Менеджер графа данных для трассировки.
        :param min_confidence: Минимальный порог уверенности для создания отдельного узла паттерна.
        """
        # Собираем данные со всех доступных ТФ
        tf_data = self._collect_all_timeframe_data(context)
        
        if not tf_data:
            return self._empty_result("No market data in context")
        
        # Анализируем каждый ТФ отдельно
        per_timeframe_results = {}
        for timeframe, df in tf_data.items():
            if df is None or len(df) < 10:
                continue
            
            result = self._analyze_single_timeframe(df, timeframe)
            per_timeframe_results[timeframe] = result
        
        if not per_timeframe_results:
            return self._empty_result("No valid data on any timeframe")
        
        # Агрегируем результаты через MultiTFContextAggregator
        aggregated = self.aggregator.aggregate_pattern_signals(per_timeframe_results)
        self.lineage = LineageTracker.create_calculated(
            method="pattern_recognition_multi_tf",
            dependencies=[context.data_lineage] if getattr(context, 'data_lineage', None) else [],
            quality=DataQuality.MEDIUM if aggregated["confidence"] > 0.5 else DataQuality.LOW,
            metadata={"timeframes": list(per_timeframe_results.keys())}
        )
        
        result = {
            "signal": aggregated["signal"],
            "confidence": aggregated["confidence"],
            "details": aggregated["details"],
            "per_timeframe_results": per_timeframe_results,
            "multi_tf_context": aggregated.get("multi_tf_context"),
            "lineage": self.lineage
        }
        return result
    
    def _collect_all_timeframe_data(self, context) -> Dict[str, Any]:
        """Собирает данные со всех доступных ТФ (базовых + синтетических)."""
        tf_data = {}
        
        # Базовые данные
        if context.market_data:
            for symbol, df in context.market_data.items():
                tf_data[context.timeframe] = df
                break  # Берем первый символ
        
        # Синтетические ТФ
        if context.synthetic_data:
            for tf, data_tuple in context.synthetic_data.items():
                if isinstance(data_tuple, tuple) and len(data_tuple) > 0:
                    tf_data[tf] = data_tuple[0]  # DataFrame
                else:
                    tf_data[tf] = data_tuple
        
        return tf_data
    
    def _analyze_single_timeframe(self, df, timeframe: str) -> Dict[str, Any]:
        """Анализ паттернов на одном ТФ с генерацией прогнозов."""
        # 1. Анализ свечных паттернов (Микро)
        candle_patterns = self._analyze_candlestick_patterns(df)
        
        # 2. Анализ графических фигур (Макро)
        chart_patterns = self._analyze_chart_patterns(df)
        
        # Агрегация результатов
        signal, confidence, details = self._aggregate_signals(candle_patterns, chart_patterns)
        
        # 3. Генерация прогнозов на основе найденных паттернов
        current_price = df['close'].iloc[-1]
        forecasts = self._generate_pattern_forecasts(
            df, timeframe, current_price,
            candle_patterns, chart_patterns,
            signal, confidence
        )
        
        return {
            "timeframe": timeframe,
            "signal": signal,
            "confidence": confidence,
            "candle_patterns": candle_patterns,
            "chart_patterns": chart_patterns,
            "details": details,
            "forecasts": forecasts
        }

    def _analyze_candlestick_patterns(self, df) -> List[Dict]:
        """Поиск известных свечных паттернов на последних свечах."""
        patterns_found = []
        o = df['open'].values
        h = df['high'].values
        l = df['low'].values
        c = df['close'].values
        
        # Берем последние 5 свечей для анализа
        idx = -1
        if len(c) < 2: return patterns_found
        
        body = abs(c - o)
        range_val = h - l
        upper_shadow = h - np.maximum(o, c)
        lower_shadow = np.minimum(o, c) - l
        
        # Нормализация (чтобы не зависеть от абсолютной цены)
        avg_body = np.mean(body[-10:]) if len(body) > 10 else body[-1]
        avg_range = np.mean(range_val[-10:]) if len(range_val) > 10 else range_val[-1]
        
        if avg_body == 0: avg_body = 1e-8
        if avg_range == 0: avg_range = 1e-8

        curr_body = body[idx]
        curr_range = range_val[idx]
        curr_upper = upper_shadow[idx]
        curr_lower = lower_shadow[idx]
        curr_open = o[idx]
        curr_close = c[idx]
        is_green = curr_close > curr_open

        # 1. Молот (Hammer) / Повешенный
        if curr_lower > (curr_body * 2) and curr_upper < (curr_body * 0.5):
            if is_green:
                patterns_found.append({"type": "Hammer", "signal": 1, "strength": 0.6})
            else:
                patterns_found.append({"type": "Hanging Man", "signal": -1, "strength": 0.6})

        # 2. Доджи (Doji) - очень маленькое тело
        if curr_body < (avg_body * 0.1):
            patterns_found.append({"type": "Doji", "signal": 0, "strength": 0.4}) # Нейтрально/Разворот

        # 3. Поглощение (Engulfing) - нужно 2 свечи
        if len(c) > 1:
            prev_idx = -2
            prev_body = body[prev_idx]
            prev_open = o[prev_idx]
            prev_close = c[prev_idx]
            prev_is_green = prev_close > prev_open
            
            # Бычье поглощение
            if not prev_is_green and is_green and \
               curr_open < prev_close and curr_close > prev_open:
                patterns_found.append({"type": "Bullish Engulfing", "signal": 1, "strength": 0.8})
            
            # Медвежье поглощение
            if prev_is_green and not is_green and \
               curr_open > prev_close and curr_close < prev_open:
                patterns_found.append({"type": "Bearish Engulfing", "signal": -1, "strength": 0.8})

        # 4. Утренняя/Вечерняя звезда (Morning/Evening Star) - 3 свечи
        if len(c) > 2:
            # Утренняя звезда (бычий разворот)
            if c[-3] < o[-3] and \
               abs(c[-2] - o[-2]) < avg_body * 0.5 and \
               c[-1] > o[-1] and \
               c[-1] > (o[-3] + c[-3]) / 2:
                patterns_found.append({"type": "Morning Star", "signal": 1, "strength": 0.85})
            
            # Вечерняя звезда (медвежий разворот)
            if c[-3] > o[-3] and \
               abs(c[-2] - o[-2]) < avg_body * 0.5 and \
               c[-1] < o[-1] and \
               c[-1] < (o[-3] + c[-3]) / 2:
                patterns_found.append({"type": "Evening Star", "signal": -1, "strength": 0.85})

        # 5. Пин-бар (Pin Bar) - длинная тень с одной стороны
        if curr_lower > (curr_body * 2) and curr_upper < curr_body:
            patterns_found.append({"type": "Bullish Pin Bar", "signal": 1, "strength": 0.65})
        elif curr_upper > (curr_body * 2) and curr_lower < curr_body:
            patterns_found.append({"type": "Bearish Pin Bar", "signal": -1, "strength": 0.65})

        # 6. Внутренний бар (Inside Bar) - диапазон внутри предыдущей свечи
        if len(c) > 1:
            if h[idx] < h[-2] and l[idx] > l[-2]:
                patterns_found.append({"type": "Inside Bar", "signal": 0, "strength": 0.5})
        self.lineage_manager = lineage_manager
        self.min_confidence = min_confidence
        self.logger = logging.getLogger(__name__)

    def scan(self, snapshot_id: str, candles: List[Dict[str, Any]], symbol: str, tf: str) -> Dict[str, Any]:
        """
        Сканирует свечи на наличие паттернов, создает узлы для значимых находок
        и возвращает агрегированный результат.

        :param snapshot_id: ID корневого снимка рынка.
        :param candles: Список свечей (OHLCV).
        :param symbol: Тикер.
        :param tf: Таймфрейм.
        :return: Словарь с общим скором, ID узлов и деталями.
        """
        if len(candles) < 3:
            return {
                'score': 0.0,
                'summary_node_id': None,
                'detail_node_ids': [],
                'patterns_found': [],
                'message': 'Insufficient data for pattern recognition'
            }

        total_score = 0.0
        total_weight = 0.0
        
        # Свечные паттерны весят меньше (краткосрок)
        for p in candle_patterns:
            if p['signal'] != 0:
                total_score += p['signal'] * p['strength'] * 0.4
                total_weight += 0.4
        
        # Графические фигуры весят больше (среднесрок)
        for p in chart_patterns:
            if p['signal'] != 0:
                total_score += p['signal'] * p['strength'] * 1.0
                total_weight += 1.0

        if total_weight == 0:
            return 0, 0.0, {"candles": candle_patterns, "charts": chart_patterns}

        normalized_score = total_score / total_weight
        
        # Конвертируем score (-1..1) в confidence (0..1) и direction
        confidence = abs(normalized_score)
        signal = 1 if normalized_score > 0 else (-1 if normalized_score < 0 else 0)
        
        # Минимальный порог уверенности
        if confidence < 0.3:
            signal = 0
            confidence = 0.0

        return signal, min(confidence, 1.0), {
            "candles": candle_patterns,
            "charts": chart_patterns,
            "dominant_pattern": chart_patterns[0]['type'] if chart_patterns else (candle_patterns[0]['type'] if candle_patterns else None)
        }

    def _generate_pattern_forecasts(self, df, timeframe, current_price, 
                                    candle_patterns, chart_patterns, 
                                    signal, confidence) -> List[Dict]:
        """
        Генерирует прогнозы на основе найденных паттернов.
        
        Логика:
        - Свечные паттерны → краткосрочные прогнозы (1-3 свечи)
        - Графические фигуры → среднесрочные прогнозы (5-10 свечей)
        - Используем целевые уровни из паттернов (H&S, треугольники и т.д.)
        """
        forecasts = []
        tf_minutes = self._get_tf_minutes(timeframe)
        
        # Рассчитываем ATR для определения диапазонов
        atr = df['high'].rolling(14).mean().iloc[-1] - df['low'].rolling(14).mean().iloc[-1]
        if pd.isna(atr) or atr == 0:
            atr = current_price * 0.01  # 1% fallback
        
        # Горизонты для свечных паттернов (краткосрочные)
        candle_horizons = [1, 3]
        
        # Горизонты для графических фигур (среднесрочные)
        chart_horizons = [5, 10]
        
        # 1. Прогнозы на основе свечных паттернов
        for pattern in candle_patterns:
            if pattern['signal'] == 0:
                continue
                
            pattern_type = pattern['type']
            pattern_signal = pattern['signal']
            pattern_strength = pattern['strength']
            
            for horizon_candles in candle_horizons:
                horizon_minutes = horizon_candles * tf_minutes
                
                # Определяем сценарий и целевую цену
                if pattern_signal > 0:
                    # Бычий паттерн
                    if 'Engulfing' in pattern_type or 'Morning Star' in pattern_type:
                        scenario = "PATTERN_REVERSAL_UP"
                        price_target = current_price + (atr * 1.5)
                        factors = [f"pattern_{pattern_type.lower().replace(' ', '_')}", "reversal_signal"]
                    elif 'Hammer' in pattern_type:
                        scenario = "PATTERN_BOUNCE"
                        price_target = current_price + (atr * 1.0)
                        factors = [f"pattern_{pattern_type.lower()}", "support_test"]
                    elif 'Three White Soldiers' in pattern_type:
                        scenario = "PATTERN_CONTINUATION_UP"
                        price_target = current_price + (atr * 2.0)
                        factors = [f"pattern_three_white_soldiers", "strong_momentum"]
                    else:
                        scenario = "PATTERN_UP"
                        price_target = current_price + (atr * 1.0)
                        factors = [f"pattern_{pattern_type.lower().replace(' ', '_')}"]
                else:
                    # Медвежий паттерн
                    if 'Engulfing' in pattern_type or 'Evening Star' in pattern_type:
                        scenario = "PATTERN_REVERSAL_DOWN"
                        price_target = current_price - (atr * 1.5)
                        factors = [f"pattern_{pattern_type.lower().replace(' ', '_')}", "reversal_signal"]
                    elif 'Hanging Man' in pattern_type:
                        scenario = "PATTERN_REJECTION"
                        price_target = current_price - (atr * 1.0)
                        factors = [f"pattern_{pattern_type.lower().replace(' ', '_')}", "resistance_test"]
                    elif 'Three Black Crows' in pattern_type:
                        scenario = "PATTERN_CONTINUATION_DOWN"
                        price_target = current_price - (atr * 2.0)
                        factors = [f"pattern_three_black_crows", "strong_momentum"]
                    else:
                        scenario = "PATTERN_DOWN"
                        price_target = current_price - (atr * 1.0)
                        factors = [f"pattern_{pattern_type.lower().replace(' ', '_')}"]
                
                # Диапазон цен
                price_range_width = atr * 0.5
                price_range = {
                    "min": min(current_price, price_target) - price_range_width,
                    "max": max(current_price, price_target) + price_range_width
                }
                
                # Уверенность зависит от силы паттерна
                forecast_confidence = pattern_strength * 0.9  # Немного снижаем для консервативности
                
                # Создаём lineage для прогноза
                forecast_lineage = LineageTracker.create_calculated(
                    method=f"pattern_forecast_{pattern_type.replace(' ', '_')}_{horizon_candles}c",
                    dependencies=[],
                    quality=DataQuality.MEDIUM,
                    metadata={
                        'pattern_type': pattern_type,
                        'pattern_signal': pattern_signal,
                        'pattern_strength': pattern_strength,
                        'horizon_candles': horizon_candles,
                        'current_price': current_price
                    }
                )
                
                forecasts.append({
                    "timeframe": timeframe,
                    "horizon_candles": horizon_candles,
                    "horizon_minutes": horizon_minutes,
                    "scenario": scenario,
                    "price_target": round(price_target, 6),
                    "price_range": {
                        "min": round(price_range["min"], 6),
                        "max": round(price_range["max"], 6)
                    },
                    "confidence": round(forecast_confidence, 3),
                    "strength": round(pattern_strength, 3),
                    "factors": factors,
                    "lineage": forecast_lineage
                })
        
        # 2. Прогнозы на основе графических фигур
        for pattern in chart_patterns:
            if pattern['signal'] == 0:
                continue
                
            pattern_type = pattern['type']
            pattern_signal = pattern['signal']
            pattern_strength = pattern['strength']
            
            for horizon_candles in chart_horizons:
                horizon_minutes = horizon_candles * tf_minutes
                
                # Определяем сценарий и целевую цену
                if pattern_signal > 0:
                    # Бычий паттерн
                    if 'Head and Shoulders' in pattern_type and 'Inverse' in pattern_type:
                        scenario = "CHART_REVERSAL_UP"
                        # Используем целевой уровень из паттерна, если есть
                        if 'target' in pattern:
                            price_target = pattern['target']
                        else:
                            price_target = current_price + (atr * 3.0)
                        factors = ["inverse_head_shoulders", "major_reversal"]
                    elif 'Double Bottom' in pattern_type:
                        scenario = "CHART_DOUBLE_BOTTOM"
                        price_target = current_price + (atr * 2.5)
                        factors = ["double_bottom", "support_confirmed"]
                    elif 'Ascending Triangle' in pattern_type:
                        scenario = "CHART_BREAKOUT_UP"
                        price_target = current_price + (atr * 2.0)
                        factors = ["ascending_triangle", "breakout_expected"]
                    elif 'Bull Flag' in pattern_type:
                        scenario = "CHART_CONTINUATION_UP"
                        price_target = current_price + (atr * 2.5)
                        factors = ["bull_flag", "continuation_pattern"]
                    elif 'Cup' in pattern_type:
                        scenario = "CHART_CUP_HANDLE"
                        price_target = current_price + (atr * 2.0)
                        factors = ["cup_and_handle", "accumulation"]
                    else:
                        scenario = "CHART_PATTERN_UP"
                        price_target = current_price + (atr * 2.0)
                        factors = [f"chart_{pattern_type.lower().replace(' ', '_')}"]
                else:
                    # Медвежий паттерн
                    if 'Head and Shoulders' in pattern_type and 'Top' in pattern_type:
                        scenario = "CHART_REVERSAL_DOWN"
                        # Используем целевой уровень из паттерна, если есть
                        if 'target' in pattern:
                            price_target = pattern['target']
                        else:
                            price_target = current_price - (atr * 3.0)
                        factors = ["head_shoulders_top", "major_reversal"]
                    elif 'Double Top' in pattern_type:
                        scenario = "CHART_DOUBLE_TOP"
                        price_target = current_price - (atr * 2.5)
                        factors = ["double_top", "resistance_confirmed"]
                    elif 'Descending Triangle' in pattern_type:
                        scenario = "CHART_BREAKDOWN"
                        price_target = current_price - (atr * 2.0)
                        factors = ["descending_triangle", "breakdown_expected"]
                    elif 'Bear Flag' in pattern_type:
                        scenario = "CHART_CONTINUATION_DOWN"
                        price_target = current_price - (atr * 2.5)
                        factors = ["bear_flag", "continuation_pattern"]
                    else:
                        scenario = "CHART_PATTERN_DOWN"
                        price_target = current_price - (atr * 2.0)
                        factors = [f"chart_{pattern_type.lower().replace(' ', '_')}"]
                
                # Диапазон цен (шире для графических фигур)
                price_range_width = atr * 1.0
                price_range = {
                    "min": min(current_price, price_target) - price_range_width,
                    "max": max(current_price, price_target) + price_range_width
                }
                
                # Уверенность зависит от силы паттерна
                forecast_confidence = pattern_strength * 0.85
                
                # Создаём lineage для прогноза
                forecast_lineage = LineageTracker.create_calculated(
                    method=f"chart_pattern_forecast_{pattern_type.replace(' ', '_')}_{horizon_candles}c",
                    dependencies=[],
                    quality=DataQuality.MEDIUM,
                    metadata={
                        'pattern_type': pattern_type,
                        'pattern_signal': pattern_signal,
                        'pattern_strength': pattern_strength,
                        'horizon_candles': horizon_candles,
                        'current_price': current_price
                    }
                )
                
                forecasts.append({
                    "timeframe": timeframe,
                    "horizon_candles": horizon_candles,
                    "horizon_minutes": horizon_minutes,
                    "scenario": scenario,
                    "price_target": round(price_target, 6),
                    "price_range": {
                        "min": round(price_range["min"], 6),
                        "max": round(price_range["max"], 6)
                    },
                    "confidence": round(forecast_confidence, 3),
                    "strength": round(pattern_strength, 3),
                    "factors": factors,
                    "lineage": forecast_lineage
                })
        
        return forecasts
    
    def _get_tf_minutes(self, timeframe):
        """Конвертирует таймфрейм в минуты"""
        mapping = {
            '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
            '1h': 60, '2h': 120, '4h': 240, '6h': 360, '12h': 720,
            '1d': 1440, '3d': 4320, '1w': 10080
        }
        return mapping.get(timeframe, 5)

    def _empty_result(self, reason: str) -> Dict:
        return {
            "signal": 0,
            "confidence": 0.0,
            "details": {"reason": reason},
            "lineage": self.lineage
        }
        detail_node_ids = []
        patterns_found = []
        bullish_count = 0
        bearish_count = 0
        dominant_pattern = None
        max_strength = 0.0

        try:
            # Проход по свечам (начиная с 3-й, так как некоторые паттерны требуют 3 свечи)
            for i in range(2, len(candles)):
                current = candles[i]
                prev1 = candles[i-1]
                prev2 = candles[i-2]

                detected_patterns = self._detect_patterns(current, prev1, prev2)

                for p_name, direction in detected_patterns:
                    weight = self.PATTERN_WEIGHTS.get(p_name, 0.0)
                    strength = abs(weight)
                    
                    # Расчет локальной уверенности на основе силы паттерна и объема
                    # Усиливаем сигнал, если объем текущей свечи выше среднего
                    avg_vol = sum(c['volume'] for c in candles[max(0, i-5):i+1]) / min(6, i+1)
                    vol_multiplier = min(1.5, current['volume'] / avg_vol) if avg_vol > 0 else 1.0
                    
                    local_confidence = min(1.0, strength * vol_multiplier)

                    if local_confidence >= self.min_confidence:
                        # Создаем узел для значимого паттерна
                        try:
                            node_id = self.lineage_manager.create_analysis_node(
                                parent_snapshot_id=snapshot_id,
                                analyzer_name=f"pattern_{p_name}",
                                result_vector={
                                    'type': p_name,
                                    'direction': direction, # 1 или -1
                                    'weight': weight,
                                    'candle_index': i,
                                    'close': current['close'],
                                    'volume_multiplier': round(vol_multiplier, 2)
                                },
                                confidence=local_confidence,
                                additional_meta={
                                    'symbol': symbol,
                                    'timeframe': tf,
                                    'detection_method': 'candle_geometry'
                                }
                            )
                            detail_node_ids.append(node_id)
                            
                            # Агрегация статистики
                            total_score += weight * direction # Направление уже учтено в весе, но для ясности
                            if direction > 0:
                                bullish_count += 1
                            else:
                                bearish_count += 1
                            
                            if strength > max_strength:
                                max_strength = strength
                                dominant_pattern = p_name

                            patterns_found.append({
                                'name': p_name,
                                'index': i,
                                'confidence': local_confidence
                            })
                        except Exception as e:
                            self.logger.error(f"Failed to create lineage node for pattern {p_name}: {e}")

            # Формирование итогового вектора
            final_score = total_score
            # Нормализация скора к диапазону [-1, 1] примерно
            normalized_score = max(-1.0, min(1.0, final_score / 5.0)) 

            # Создание финального узла-агрегатора
            summary_vector = {
                'total_raw_score': total_score,
                'normalized_score': normalized_score,
                'bullish_count': bullish_count,
                'bearish_count': bearish_count,
                'dominant_pattern': dominant_pattern or 'none',
                'total_detected': len(patterns_found)
            }

            summary_node_id = self.lineage_manager.create_analysis_node(
                parent_snapshot_id=snapshot_id,
                analyzer_name=f"patterns_summary_{tf}",
                result_vector=summary_vector,
                confidence=max(0.1, min(1.0, abs(normalized_score))), # Уверенность в итоговом сигнале
                additional_meta={
                    'symbol': symbol,
                    'timeframe': tf,
                    'scan_range': len(candles)
                }
            )

            return {
                'score': normalized_score,
                'raw_score': total_score,
                'summary_node_id': summary_node_id,
                'detail_node_ids': detail_node_ids,
                'patterns_found': patterns_found,
                'dominant': dominant_pattern,
                'status': 'success'
            }

        except Exception as e:
            self.logger.error(f"Critical error in pattern scanning ({symbol} {tf}): {e}", exc_info=True)
            return {
                'score': 0.0,
                'summary_node_id': None,
                'detail_node_ids': [],
                'patterns_found': [],
                'error': str(e),
                'status': 'error'
            }

    def _detect_patterns(self, curr: Dict, prev1: Dict, prev2: Dict) -> List[tuple]:
        """
        Внутренний метод распознавания паттернов на основе 3 свечей.
        Возвращает список кортежей (name, direction).
        """
        patterns = []
        
        o, h, l, c = curr['open'], curr['high'], curr['low'], curr['close']
        o1, h1, l1, c1 = prev1['open'], prev1['high'], prev1['low'], prev1['close']
        o2, h2, l2, c2 = prev2['open'], prev2['high'], prev2['low'], prev2['close']

        body_curr = abs(c - o)
        body_prev = abs(c1 - o1)
        range_curr = h - l
        range_prev = h1 - l1
        
        is_green = c > o
        is_red = c < o
        is_green_prev = c1 > o1
        is_red_prev = c1 < o1

        # Doji
        if body_curr < (range_curr * 0.1):
            patterns.append(('doji', 0)) # Нейтральный, но важен в контексте

        # Hammer / Hanging Man
        lower_shadow = min(o, c) - l
        upper_shadow = h - max(o, c)
        if lower_shadow > (body_curr * 2) and upper_shadow < (body_curr * 0.5):
            if is_green: # Hammer (бычий разворот после падения)
                patterns.append(('hammer', 1))
            else: # Hanging Man (медвежий разворот после роста)
                patterns.append(('hanging_man', -1))

        # Shooting Star / Inverted Hammer
        if upper_shadow > (body_curr * 2) and lower_shadow < (body_curr * 0.5):
            if is_green: # Inverted Hammer (бычий, но слабый)
                patterns.append(('inverted_hammer', 1))
            else: # Shooting Star (медвежий разворот)
                patterns.append(('shooting_star', -1))

        # Engulfing
        if is_green and is_red_prev and c > o1 and o < c1 and body_curr > body_prev:
            patterns.append(('bullish_engulfing', 1))
        elif is_red and is_green_prev and c < o1 and o > c1 and body_curr > body_prev:
            patterns.append(('bearish_engulfing', -1))

        # Morning Star / Evening Star (упрощенно)
        if is_red_prev and body_prev < (range_prev * 0.3): # Маленькая средняя свеча
            if is_red and c < c2 and c < (c2 + o2)/2: # Третья вниз
                 pass # Evening Star требует специфичной формы, здесь заглушка логики
            if is_green and c > c2 and c > (c2 + o2)/2: # Третья вверх
                 patterns.append(('morning_star', 1))
        
        # Простая проверка на сильные трендовые свечи (Three Soldiers/Crows эвристика)
        if body_curr > (range_curr * 0.7):
            if is_green and is_green_prev:
                patterns.append(('three_white_soldiers', 1)) # Упрощенно
            elif is_red and is_red_prev:
                patterns.append(('three_black_crows', -1))

        return patterns
