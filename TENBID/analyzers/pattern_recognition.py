"""
Pattern Recognition Analyzer
Анализирует свечные паттерны (микро) и графические фигуры (макро).
Возвращает сигнал и уровень уверенности на основе найденных фигур.
"""
import numpy as np
from typing import Dict, Any, List, Tuple
from datetime import datetime
from core.data_lineage import DataLineage, DataSource, DataQuality

class PatternRecognitionAnalyzer:
    def __init__(self):
        self.lineage = DataLineage(
            source=DataSource.CALCULATED,
            quality=DataQuality.MEDIUM,
            timestamp=datetime.now(),
            calculation_method="pattern_recognition",
            metadata={"version": "1.0", "type": "candlestick_and_chart_patterns"}
        )
        
    def analyze(self, context) -> Dict[str, Any]:
        """
        Полный анализ паттернов.
        """
        # Получаем данные из контекста - используем первый символ в market_data
        if not context.market_data:
            return self._empty_result("No market data in context")
        
        # Берем данные для первого доступного символа (обычно тот же symbol что и в контексте)
        symbol = next(iter(context.market_data.keys()), None)
        if not symbol:
            return self._empty_result("No symbol found in market_data")
            
        df = context.market_data[symbol]
        
        if df is None or len(df) < 10:
            return self._empty_result(f"No data or insufficient data (len={len(df) if df is not None else 0})")

        # 1. Анализ свечных паттернов (Микро)
        candle_patterns = self._analyze_candlestick_patterns(df)
        
        # 2. Анализ графических фигур (Макро)
        chart_patterns = self._analyze_chart_patterns(df)
        
        # Агрегация результатов
        signal, confidence, details = self._aggregate_signals(candle_patterns, chart_patterns)
        
        result = {
            "signal": signal, # 1 (buy), -1 (sell), 0 (neutral)
            "confidence": confidence, # 0.0 - 1.0
            "details": details,
            "lineage": self.lineage
        }
        return result

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

    def _empty_result(self, reason: str) -> Dict:
        return {
            "signal": 0,
            "confidence": 0.0,
            "details": {"reason": reason},
            "lineage": self.lineage
        }
