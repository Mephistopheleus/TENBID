import logging
from typing import Dict, List, Any, Optional, Tuple
from core.data_lineage import DataLineageManager

logger = logging.getLogger(__name__)

class SupportResistanceAnalyzer:
    """
    Анализатор уровней поддержки и сопротивления.
    Находит ключевые зоны на основе локальных экстремумов (пивотов),
    кластеризует их и оценивает силу.
    """

    def __init__(self, lineage_manager: DataLineageManager, 
                 pivot_lookback: int = 5, 
                 min_touches: int = 2,
                 cluster_tolerance_pct: float = 0.005):
        """
        :param lineage_manager: Менеджер графа данных.
        :param pivot_lookback: Количество баров слева/справа для определения пивота.
        :param min_touches: Минимальное количество касаний для значимости уровня.
        :param cluster_tolerance_pct: Допуск для объединения близких цен в зону (0.5%).
        """
        self.lineage_manager = lineage_manager
        self.pivot_lookback = pivot_lookback
        self.min_touches = min_touches
        self.cluster_tolerance_pct = cluster_tolerance_pct
        self.logger = logging.getLogger(__name__)

    def find_levels(self, snapshot_id: str, candles: List[Dict[str, Any]], 
                    symbol: str, tf: str) -> Dict[str, Any]:
        """
        Находит уровни поддержки и сопротивления, создает узел lineage и возвращает результат.
        
        :param snapshot_id: ID корневого снимка рынка.
        :param candles: Список свечей (OHLCV).
        :param symbol: Тикер.
        :param tf: Таймфрейм.
        :return: Словарь с уровнями, node_id и метриками.
        """
        if len(candles) < (self.pivot_lookback * 2 + 1):
            return {
                'status': 'error',
                'message': 'Insufficient data for S/R analysis',
                'levels': [],
                'node_id': None
            }

        try:
            # 1. Поиск локальных экстремумов (Pivots)
            pivots = self._find_pivots(candles)
            
            if not pivots:
                return {
                    'status': 'success',
                    'message': 'No significant pivots found',
                    'levels': [],
                    'node_id': None
                }

            # 2. Кластеризация пивотов в зоны (Levels)
            raw_levels = self._cluster_levels(pivots, candles)

            # 3. Оценка силы уровней
            scored_levels = self._score_levels(raw_levels, candles)

            # Фильтрация слабых уровней
            significant_levels = [lvl for lvl in scored_levels if lvl['strength'] >= 0.3]
            
            # Сортировка по силе
            significant_levels.sort(key=lambda x: x['strength'], reverse=True)

            # Берем топ-10 для отчета, чтобы не перегружать контекст
            top_levels = significant_levels[:10]

            # 4. Подготовка данных для узла Lineage
            levels_vector = []
            nearest_support = None
            nearest_resistance = None
            current_price = candles[-1]['close']

            for lvl in top_levels:
                level_entry = {
                    'price': round(lvl['price'], 8),
                    'type': lvl['type'], # 'support' или 'resistance'
                    'strength': round(lvl['strength'], 3),
                    'touches': lvl['touches'],
                    'last_touch_bar': lvl['last_touch_idx']
                }
                levels_vector.append(level_entry)

                # Определение ближайших уровней
                dist = abs(lvl['price'] - current_price)
                if lvl['type'] == 'support':
                    if lvl['price'] <= current_price:
                        if nearest_support is None or (current_price - lvl['price']) < (current_price - nearest_support['price']):
                            nearest_support = lvl
                elif lvl['type'] == 'resistance':
                    if lvl['price'] >= current_price:
                        if nearest_resistance is None or (lvl['price'] - current_price) < (nearest_resistance['price'] - current_price):
                            nearest_resistance = lvl

            # Расчет общей уверенности анализатора
            # Зависит от количества сильных уровней и их средней силы
            if not significant_levels:
                confidence_score = 0.1
            else:
                avg_strength = sum(l['strength'] for l in significant_levels) / len(significant_levels)
                count_bonus = min(1.0, len(significant_levels) / 5.0) # Бонус за количество (до 5 уровней)
                confidence_score = (avg_strength * 0.7) + (count_bonus * 0.3)

            # 5. Создание узла Lineage
            result_vector = {
                'levels': levels_vector,
                'nearest_support': nearest_support['price'] if nearest_support else None,
                'nearest_resistance': nearest_resistance['price'] if nearest_resistance else None,
                'total_significant': len(significant_levels),
                'market_structure': 'ranging' if (nearest_support and nearest_resistance) else 'trending'
            }

            node_id = self.lineage_manager.create_analysis_node(
                parent_snapshot_id=snapshot_id,
                analyzer_name=f"support_resistance_{tf}",
                result_vector=result_vector,
                confidence=confidence_score,
                additional_meta={
                    'symbol': symbol,
                    'timeframe': tf,
                    'pivot_lookback': self.pivot_lookback,
                    'total_pivots_found': len(pivots)
                }
            )

            return {
                'status': 'success',
                'node_id': node_id,
                'levels': top_levels, # Полные объекты для внутренней логики
                'nearest_sr': {
                    'support': nearest_support,
                    'resistance': nearest_resistance
                },
                'confidence': confidence_score,
                'details': f"Found {len(significant_levels)} significant levels"
            }

        except Exception as e:
            self.logger.error(f"Error in S/R analysis ({symbol} {tf}): {e}", exc_info=True)
            return {
                'status': 'error',
                'message': str(e),
                'levels': [],
                'node_id': None
            }

    def _find_pivots(self, candles: List[Dict]) -> List[Dict]:
        """Находит локальные максимумы и минимумы."""
        pivots = []
        n = len(candles)
        lookback = self.pivot_lookback

        for i in range(lookback, n - lookback):
            current_high = candles[i]['high']
            current_low = candles[i]['low']

            is_high_pivot = True
            is_low_pivot = True

            for j in range(1, lookback + 1):
                if candles[i+j]['high'] >= current_high or candles[i-j]['high'] >= current_high:
                    is_high_pivot = False
                if candles[i+j]['low'] <= current_low or candles[i-j]['low'] <= current_low:
                    is_low_pivot = False
            
            if is_high_pivot:
                pivots.append({'index': i, 'price': current_high, 'type': 'high'})
            elif is_low_pivot:
                pivots.append({'index': i, 'price': current_low, 'type': 'low'})

        return pivots

    def _cluster_levels(self, pivots: List[Dict], candles: List[Dict]) -> List[Dict]:
        """Группирует близкие пивоты в зоны."""
        if not pivots:
            return []

        # Разделяем на highs и lows
        highs = [p for p in pivots if p['type'] == 'high']
        lows = [p for p in pivots if p['type'] == 'low']

        clusters = []

        # Функция кластеризации для одного типа
        def cluster_group(group, level_type):
            if not group:
                return []
            
            group.sort(key=lambda x: x['price'])
            local_clusters = []
            current_cluster = [group[0]]

            for i in range(1, len(group)):
                prev_price = current_cluster[-1]['price']
                curr_price = group[i]['price']
                tolerance = prev_price * self.cluster_tolerance_pct

                if abs(curr_price - prev_price) <= tolerance:
                    current_cluster.append(group[i])
                else:
                    # Сохраняем средний уровень кластера
                    avg_price = sum(c['price'] for c in current_cluster) / len(current_cluster)
                    indices = [c['index'] for c in current_cluster]
                    local_clusters.append({
                        'price': avg_price,
                        'type': level_type,
                        'indices': indices,
                        'touches': len(current_cluster)
                    })
                    current_cluster = [group[i]]
            
            # Последний кластер
            if current_cluster:
                avg_price = sum(c['price'] for c in current_cluster) / len(current_cluster)
                indices = [c['index'] for c in current_cluster]
                local_clusters.append({
                    'price': avg_price,
                    'type': level_type,
                    'indices': indices,
                    'touches': len(current_cluster)
                })
            
            return local_clusters

        clusters.extend(cluster_group(highs, 'resistance'))
        clusters.extend(cluster_group(lows, 'support'))

        return clusters

    def _score_levels(self, levels: List[Dict], candles: List[Dict]) -> List[Dict]:
        """Оценивает силу уровней на основе касаний, объема и свежести."""
        scored = []
        current_idx = len(candles) - 1

        for lvl in levels:
            score = 0.0
            
            # 1. Базовый скор за количество касаний (логарифмический рост)
            import math
            touch_score = math.log(lvl['touches'] + 1) / math.log(4) # Нормализация
            score += touch_score * 0.4

            # 2. Объем в точках касания (если есть данные)
            # Упрощенно: считаем средний объем вокруг индексов
            vol_sum = 0
            valid_touches = 0
            for idx in lvl['indices']:
                if 0 <= idx < len(candles):
                    vol_sum += candles[idx]['volume']
                    valid_touches += 1
            
            avg_vol = vol_sum / valid_touches if valid_touches > 0 else 0
            total_avg_vol = sum(c['volume'] for c in candles) / len(candles)
            vol_ratio = avg_vol / total_avg_vol if total_avg_vol > 0 else 1.0
            
            vol_score = min(1.5, vol_ratio) # Ограничиваем влияние объема
            score += vol_score * 0.3

            # 3. Свежесть (чем ближе последний тест к текущему моменту, тем лучше)
            last_touch = max(lvl['indices']) if lvl['indices'] else 0
            distance = current_idx - last_touch
            freshness_score = max(0.1, 1.0 - (distance / len(candles)))
            score += freshness_score * 0.3

            lvl['strength'] = min(1.0, score)
            lvl['last_touch_idx'] = last_touch
            scored.append(lvl)

        return scored
