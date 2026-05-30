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
        """
        Полный анализ паттернов с поддержкой мульти-ТФ.
        Анализирует паттерны на всех доступных таймфреймах и агрегирует результаты.
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

        # 7. Внешний бар (Outside Bar / Engulfing Range)
        if len(c) > 1:
            if h[idx] > h[-2] and l[idx] < l[-2]:
                patterns_found.append({"type": "Outside Bar", "signal": 0, "strength": 0.55})

        # 8. Три белых солдата / Три черные вороны
        if len(c) > 3:
            # Три белых солдата
            if all(c[i] > o[i] for i in [-1, -2, -3]) and \
               all(c[i] > c[i+1] for i in [-3, -2]):
                patterns_found.append({"type": "Three White Soldiers", "signal": 1, "strength": 0.9})
            
            # Три черные вороны
            if all(c[i] < o[i] for i in [-1, -2, -3]) and \
               all(c[i] < c[i+1] for i in [-3, -2]):
                patterns_found.append({"type": "Three Black Crows", "signal": -1, "strength": 0.9})

        return patterns_found

    def _analyze_chart_patterns(self, df) -> List[Dict]:
        """
        Поиск глобальных фигур: Голова и плечи, Чашка с ручкой, Треугольники.
        Использует упрощенный алгоритм поиска экстремумов (Pivot Points).
        """
        patterns_found = []
        highs = df['high'].values
        lows = df['low'].values
        n = len(highs)
        if n < 20: return patterns_found

        # Поиск локальных экстремумов (окно 5 свечей)
        window = 5
        pivots_h = []
        pivots_l = []
        
        for i in range(window, n - window):
            if highs[i] == max(highs[i-window:i+window+1]):
                pivots_h.append((i, highs[i]))
            if lows[i] == min(lows[i-window:i+window+1]):
                pivots_l.append((i, lows[i]))

        # 1. Голова и Плечи (Head and Shoulders)
        # Ищем 3 пика: Левый < Центральный > Правый, при этом Центральный максимален
        if len(pivots_h) >= 3:
            # Берем последние 3 пика
            last_3_peaks = pivots_h[-3:]
            l_peak, c_peak, r_peak = last_3_peaks
            
            # Условия: Центр выше левого и правого, левый и правый примерно равны (допуск 10%)
            if c_peak[1] > l_peak[1] and c_peak[1] > r_peak[1]:
                if abs(l_peak[1] - r_peak[1]) / c_peak[1] < 0.1:
                    patterns_found.append({
                        "type": "Head and Shoulders (Top)", 
                        "signal": -1, 
                        "strength": 0.85,
                        "target": l_peak[1] - (c_peak[1] - l_peak[1]) # Примерная цель
                    })
        
        # Инверсная голова и плечи (дно)
        if len(pivots_l) >= 3:
            last_3_troughs = pivots_l[-3:]
            l_trough, c_trough, r_trough = last_3_troughs
            
            if c_trough[1] < l_trough[1] and c_trough[1] < r_trough[1]:
                if abs(l_trough[1] - r_trough[1]) / c_trough[1] < 0.1:
                    patterns_found.append({
                        "type": "Inverse Head and Shoulders (Bottom)", 
                        "signal": 1, 
                        "strength": 0.85
                    })

        # 2. Двойная вершина/дно (Double Top/Bottom)
        if len(pivots_h) >= 2:
            p1, p2 = pivots_h[-2], pivots_h[-1]
            if abs(p1[1] - p2[1]) / p1[1] < 0.05: # Разница менее 5%
                 patterns_found.append({"type": "Double Top", "signal": -1, "strength": 0.75})
                 
        if len(pivots_l) >= 2:
            p1, p2 = pivots_l[-2], pivots_l[-1]
            if abs(p1[1] - p2[1]) / p1[1] < 0.05:
                 patterns_found.append({"type": "Double Bottom", "signal": 1, "strength": 0.75})

        # 3. Чашка с ручкой (Cup and Handle) - эвристика
        if n > 50:
            recent_high = max(highs[-20:])
            past_high = max(highs[-50:-20])
            if recent_high > past_high * 0.98 and recent_high < past_high * 1.02:
                if highs[-1] < recent_high * 0.98: 
                     patterns_found.append({"type": "Potential Cup & Handle", "signal": 1, "strength": 0.65})

        # 4. Треугольники (Triangles) - Ascending, Descending, Symmetrical
        if n > 30 and len(pivots_h) >= 3 and len(pivots_l) >= 3:
            # Берем последние 3 пика и 3 впадины
            last_peaks = pivots_h[-3:]
            last_troughs = pivots_l[-3:]
            
            # Проверяем тренды линий
            peak_slope = (last_peaks[-1][1] - last_peaks[0][1]) / (last_peaks[-1][0] - last_peaks[0][0] + 1e-8)
            trough_slope = (last_troughs[-1][1] - last_troughs[0][1]) / (last_troughs[-1][0] - last_troughs[0][0] + 1e-8)
            
            # Симметричный треугольник (сходящиеся линии)
            if peak_slope < -0.001 and trough_slope > 0.001:
                patterns_found.append({"type": "Symmetrical Triangle", "signal": 0, "strength": 0.6})
            # Восходящий треугольник (горизонтальный верх, растущий низ)
            elif abs(peak_slope) < 0.001 and trough_slope > 0.001:
                patterns_found.append({"type": "Ascending Triangle", "signal": 1, "strength": 0.7})
            # Нисходящий треугольник (падающий верх, горизонтальный низ)
            elif peak_slope < -0.001 and abs(trough_slope) < 0.001:
                patterns_found.append({"type": "Descending Triangle", "signal": -1, "strength": 0.7})

        # 5. Флаги (Flags) - бычий/медвежий флаг после сильного движения
        if n > 20:
            # Определяем сильное движение за последние 10 свечей
            price_change = (highs[-1] - highs[-10]) / highs[-10]
            
            # Бычий флаг (рост > 3%, затем консолидация)
            if price_change > 0.03:
                # Проверяем консолидацию: последние 5 свечей в узком диапазоне
                recent_range = (max(highs[-5:]) - min(lows[-5:])) / lows[-5]
                if recent_range < 0.015:
                    patterns_found.append({"type": "Bull Flag", "signal": 1, "strength": 0.65})
            
            # Медвежий флаг (падение > 3%, затем консолидация)
            elif price_change < -0.03:
                recent_range = (max(highs[-5:]) - min(lows[-5:])) / lows[-5]
                if recent_range < 0.015:
                    patterns_found.append({"type": "Bear Flag", "signal": -1, "strength": 0.65})

        return patterns_found

    def _aggregate_signals(self, candle_patterns: List, chart_patterns: List) -> Tuple[int, float, Dict]:
        """Собирает все сигналы в один итоговый."""
        if not candle_patterns and not chart_patterns:
            return 0, 0.0, {"candles": [], "charts": []}

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
