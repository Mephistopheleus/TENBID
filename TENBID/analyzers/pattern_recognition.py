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
