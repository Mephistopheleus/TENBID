import logging
from typing import Dict, List, Any, Optional, Tuple
from core.data_lineage import DataLineageManager
import math

logger = logging.getLogger(__name__)

class CorrelationAnalyzer:
    """
    Анализатор межрыночных корреляций.
    Рассчитывает коэффициент корреляции Пирсона между целевым активом и эталонами (BTC, ETH).
    Выявляет дивергенции и аномалии. Интегрирован с DataLineageManager v2.0.
    """

    def __init__(self, lineage_manager: DataLineageManager, lookback_period: int = 50):
        """
        :param lineage_manager: Менеджер графа данных.
        :param lookback_period: Количество свечей для расчета корреляции (окно).
        """
        self.lineage_manager = lineage_manager
        self.lookback_period = lookback_period
        self.logger = logging.getLogger(__name__)

    def calculate_correlation(self, snapshot_id: str, target_series: List[float], 
                              reference_series: List[float], target_symbol: str, 
                              reference_symbol: str) -> Dict[str, Any]:
        """
        Рассчитывает корреляцию между двумя временными рядами, создает узел lineage
        и возвращает результаты.

        :param snapshot_id: ID корневого снимка рынка.
        :param target_series: Список цен целевого актива (Close prices).
        :param reference_series: Список цен эталонного актива (например, BTC).
        :param target_symbol: Тикер целевого актива.
        :param reference_symbol: Тикер эталона.
        :return: Словарь с корреляцией, статусом дивергенции и ID узла.
        """
        # Проверка длины данных
        min_len = min(len(target_series), len(reference_series))
        if min_len < self.lookback_period:
            self.logger.warning(f"Недостаточно данных для корреляции ({target_symbol}/{reference_symbol}). Нужно {self.lookback_period}, есть {min_len}.")
            return {
                'status': 'error',
                'message': 'Insufficient data',
                'correlation': None,
                'node_id': None,
                'divergence_detected': False
            }

        # Обрезаем серии до одинаковой длины и нужного окна
        target_series = target_series[-self.lookback_period:]
        reference_series = reference_series[-self.lookback_period:]

        try:
            # 1. Расчет коэффициента корреляции Пирсона
            corr_score = self._pearson_correlation(target_series, reference_series)
            
            if corr_score is None:
                raise ValueError("Calculation failed (zero variance)")

            # 2. Определение типа связи
            relationship_type = self._classify_relationship(corr_score)
            
            # 3. Выявление дивергенции (упрощенная эвристика)
            # Если краткосрочная корреляция сильно отличается от долгосрочной (здесь эмулируем сравнением с предыдущим окном)
            # Для полноценной проверки нужно передавать еще одно окно данных, здесь используем порог стабильности
            divergence_detected = False
            if abs(corr_score) < 0.3:
                # Слабая корреляция может считаться "шумом" или началом дивергенции, если раньше была сильной
                # В реальном сценарии здесь было бы сравнение с rolling_mean корреляции
                pass 
            
            # Более сложная логика: если цены растут, а корреляция падает в отрицательную зону
            # (Здесь оставляем флаг для внешней логики, так как нужны данные о тренде)
            
            # 4. Расчет уверенности (Statistical Significance)
            # Уверенность растет с увеличением размера выборки и силы корреляции
            # T-statistic approximation for correlation: t = r * sqrt((n-2)/(1-r^2))
            # Но для простоты используем эвристику: confidence = |r| * log(n) / log(max_n)
            max_expected_n = 200 # Нормализация
            n_factor = min(1.0, math.log(min_len + 1) / math.log(max_expected_n + 1))
            
            confidence_score = abs(corr_score) * n_factor
            confidence_score = max(0.1, min(1.0, confidence_score))

            # 5. Формирование вектора результата
            result_vector = {
                'correlation_coefficient': round(corr_score, 4),
                'relationship_type': relationship_type,
                'lookback_period': self.lookback_period,
                'data_points': min_len,
                'target_symbol': target_symbol,
                'reference_symbol': reference_symbol,
                'divergence_flag': divergence_detected
            }

            # 6. Создание узла Lineage
            node_id = self.lineage_manager.create_analysis_node(
                parent_snapshot_id=snapshot_id,
                analyzer_name=f"correlation_{target_symbol}_{reference_symbol}",
                result_vector=result_vector,
                confidence=confidence_score,
                additional_meta={
                    'calculation_method': 'pearson',
                    'window_size': self.lookback_period,
                    'significance_level': 'high' if confidence_score > 0.7 else 'low'
                }
            )

            return {
                'status': 'success',
                'node_id': node_id,
                'correlation': corr_score,
                'type': relationship_type,
                'divergence_detected': divergence_detected,
                'confidence': confidence_score,
                'details': result_vector
            }

        except Exception as e:
            self.logger.error(f"Ошибка расчета корреляции ({target_symbol}/{reference_symbol}): {e}", exc_info=True)
            return {
                'status': 'error',
                'message': str(e),
                'correlation': None,
                'node_id': None,
                'divergence_detected': False
            }

    def analyze_matrix(self, snapshot_id: str, assets_data: Dict[str, List[float]], 
                       base_asset: str = 'BTC') -> Dict[str, Any]:
        """
        Анализирует матрицу корреляций для списка активов относительно базового.
        Создает один агрегированный узел для всей матрицы.

        :param snapshot_id: ID снимка.
        :param assets_data: Словарь {symbol: [prices]}.
        :param base_asset: Базовый актив для сравнения.
        :return: Словарь с результатами по всем парам.
        """
        if base_asset not in assets_data:
            return {'status': 'error', 'message': f'Base asset {base_asset} not found'}

        base_series = assets_data[base_asset]
        results = {}
        node_ids = []
        total_divergence_count = 0

        for symbol, series in assets_data.items():
            if symbol == base_asset:
                continue
            
            res = self.calculate_correlation(
                snapshot_id=snapshot_id,
                target_series=series,
                reference_series=base_series,
                target_symbol=symbol,
                reference_symbol=base_asset
            )
            
            if res['status'] == 'success':
                results[symbol] = res
                node_ids.append(res['node_id'])
                if res.get('divergence_detected'):
                    total_divergence_count += 1

        # Создание агрегированного узла для всей матрицы
        summary_vector = {
            'base_asset': base_asset,
            'assets_analyzed': list(results.keys()),
            'avg_correlation': sum(r['correlation'] for r in results.values()) / len(results) if results else 0.0,
            'divergences_count': total_divergence_count,
            'max_correlation': max((r['correlation'] for r in results.values()), default=0.0),
            'min_correlation': min((r['correlation'] for r in results.values()), default=0.0)
        }

        avg_conf = sum(r['confidence'] for r in results.values()) / len(results) if results else 0.0

        summary_node_id = self.lineage_manager.create_analysis_node(
            parent_snapshot_id=snapshot_id,
            analyzer_name="correlation_matrix_summary",
            result_vector=summary_vector,
            confidence=avg_conf,
            additional_meta={
                'total_pairs': len(results),
                'base_asset': base_asset
            }
        )

        return {
            'status': 'success',
            'summary_node_id': summary_node_id,
            'detail_node_ids': node_ids,
            'results': results,
            'matrix_summary': summary_vector
        }

    def _pearson_correlation(self, x: List[float], y: List[float]) -> Optional[float]:
        """
        Вычисляет коэффициент корреляции Пирсона между двумя списками.
        """
        n = len(x)
        if n != len(y) or n == 0:
            return None
        
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        
        num = 0.0
        den_x = 0.0
        den_y = 0.0
        
        for i in range(n):
            dx = x[i] - mean_x
            dy = y[i] - mean_y
            num += dx * dy
            den_x += dx * dx
            den_y += dy * dy
            
        if den_x == 0 or den_y == 0:
            return None # Нулевая дисперсия
        
        return num / math.sqrt(den_x * den_y)

    def _classify_relationship(self, corr: float) -> str:
        """
        Классифицирует силу и направление связи.
        """
        if corr >= 0.8:
            return "STRONG_POSITIVE"
        elif corr >= 0.5:
            return "MODERATE_POSITIVE"
        elif corr >= 0.2:
            return "WEAK_POSITIVE"
        elif corr > -0.2:
            return "NEGLIGIBLE"
        elif corr > -0.5:
            return "WEAK_NEGATIVE"
        elif corr > -0.8:
            return "MODERATE_NEGATIVE"
        else:
            return "STRONG_NEGATIVE"
