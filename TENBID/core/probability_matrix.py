"""
Ядро системы вероятностного моделирования.
Строит многомерную матрицу вероятностей (Время, Цена, Сценарий) -> Вероятность.
Использует Grid + Gaussian Blur для эффективной аппроксимации.
Все параметры настраиваются автотюнером.
"""
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum
from scipy.ndimage import gaussian_filter
import logging

logger = logging.getLogger(__name__)


class MarketScenario(Enum):
    """Расширенный набор рыночных сценариев"""
    # Трендовые
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    TREND_CONTINUATION_UP = "trend_continuation_up"
    TREND_CONTINUATION_DOWN = "trend_continuation_down"
    
    # Пробои
    BREAKOUT_UP = "breakout_up"
    BREAKOUT_DOWN = "breakout_down"
    RESISTANCE_BREAKOUT = "resistance_breakout"
    SUPPORT_BREAKDOWN = "support_breakdown"
    
    # Отскоки
    SUPPORT_BOUNCE = "support_bounce"
    RESISTANCE_BOUNCE = "resistance_bounce"
    
    # Развороты
    REVERSAL_UP = "reversal_up"
    REVERSAL_DOWN = "reversal_down"
    PATTERN_REVERSAL_UP = "pattern_reversal_up"
    PATTERN_REVERSAL_DOWN = "pattern_reversal_down"
    
    # Фрактальные
    FRACTAL_RESISTANCE_APPROACH = "fractal_resistance_approach"
    FRACTAL_SUPPORT_APPROACH = "fractal_support_approach"
    FRACTAL_BULLISH_REVERSAL = "fractal_bullish_reversal"
    FRACTAL_BEARISH_REVERSAL = "fractal_bearish_reversal"
    
    # Паттерны
    PATTERN_BOUNCE = "pattern_bounce"
    PATTERN_REJECTION = "pattern_rejection"
    PATTERN_CONTINUATION_UP = "pattern_continuation_up"
    PATTERN_CONTINUATION_DOWN = "pattern_continuation_down"
    CHART_BREAKOUT_UP = "chart_breakout_up"
    CHART_BREAKDOWN = "chart_breakdown"
    CHART_DOUBLE_TOP = "chart_double_top"
    CHART_DOUBLE_BOTTOM = "chart_double_bottom"
    
    # Нейтральные
    FLAT = "flat"
    CONSOLIDATION = "consolidation"


@dataclass
class ForecastInput:
    """Входной прогноз от анализатора"""
    timeframe: str
    horizon_minutes: int
    scenario: str
    price_target: float
    price_range: Dict[str, float]  # {"min": float, "max": float}
    confidence: float
    strength: float
    factors: List[str]
    analyzer_name: str
    trust_weight: float = 1.0  # Вес доверия от автотюнера


@dataclass
class ProbabilityZone:
    """Зона максимальной вероятности"""
    time_minutes: float
    price_center: float
    price_range: Tuple[float, float]
    scenario: MarketScenario
    probability: float
    contributing_forecasts: int
    dominant_timeframe: str


class ProbabilityMatrix:
    """
    Многомерное поле вероятностей с Grid + Gaussian Blur аппроксимацией.
    
    Структура:
    - 3D numpy массив: [time_steps, price_levels, scenarios]
    - Быстрый поиск зон через предварительную индексацию
    - Все параметры от автотюнера
    """
    
    def __init__(self, autotuner_params: Optional[Dict[str, Any]] = None):
        """
        Инициализация матрицы с параметрами от автотюнера.
        
        Args:
            autotuner_params: Параметры от автотюнера или None для дефолтных
        """
        # Параметры от автотюнера (с дефолтными значениями)
        params = autotuner_params or {}
        
        self.time_horizon_minutes = params.get('matrix_time_horizon', 60)
        self.time_resolution_minutes = params.get('matrix_time_resolution', 5)
        self.price_resolution_pct = params.get('matrix_price_resolution', 0.5)
        self.blur_radius = params.get('matrix_blur_radius', 1.0)
        self.min_probability_threshold = params.get('matrix_min_probability', 0.1)
        self.max_zones_to_return = params.get('matrix_max_zones', 10)
        
        # Вычисляемые параметры
        self.time_steps = int(self.time_horizon_minutes / self.time_resolution_minutes)
        self.price_levels = 100  # Фиксированное количество уровней цены
        
        # Текущее состояние
        self.current_price = 0.0
        self.price_min = 0.0
        self.price_max = 0.0
        self.price_step = 0.0
        
        # 3D матрица: [time, price, scenario]
        self.num_scenarios = len(MarketScenario)
        self.matrix = np.zeros((self.time_steps, self.price_levels, self.num_scenarios), dtype=np.float32)
        
        # Маппинг сценариев на индексы
        self.scenario_to_idx = {scenario: idx for idx, scenario in enumerate(MarketScenario)}
        self.idx_to_scenario = {idx: scenario for scenario, idx in self.scenario_to_idx.items()}
        
        # Кэш для быстрого поиска
        self._zones_cache: List[ProbabilityZone] = []
        self._cache_valid = False
        
        # Статистика
        self.forecasts_added = 0
        self.blur_applied = False
        
        logger.info(f"ProbabilityMatrix initialized: time_horizon={self.time_horizon_minutes}m, "
                   f"time_res={self.time_resolution_minutes}m, price_res={self.price_resolution_pct}%, "
                   f"blur_radius={self.blur_radius}")
    
    def initialize(self, current_price: float, volatility: float):
        """
        Инициализация сетки цен вокруг текущей цены.
        
        Args:
            current_price: Текущая цена актива
            volatility: Волатильность (ATR или стандартное отклонение)
        """
        self.current_price = current_price
        
        # Определяем диапазон цен на основе волатильности
        # Покрываем ±3 ATR от текущей цены
        price_range = max(volatility * 3, current_price * 0.05)  # Минимум 5%
        
        self.price_min = current_price - price_range
        self.price_max = current_price + price_range
        self.price_step = (self.price_max - self.price_min) / self.price_levels
        
        # Очищаем матрицу
        self.matrix.fill(0.0)
        self.forecasts_added = 0
        self.blur_applied = False
        self._cache_valid = False
        
        logger.debug(f"Matrix grid initialized: price_range=[{self.price_min:.6f}, {self.price_max:.6f}], "
                    f"step={self.price_step:.6f}")
    
    def add_forecast(self, forecast: ForecastInput):
        """
        Добавляет прогноз в матрицу с учётом веса доверия.
        
        Args:
            forecast: Прогноз от анализатора с весом доверия
        """
        # Конвертируем сценарий в enum
        try:
            scenario = MarketScenario(forecast.scenario.lower())
        except ValueError:
            logger.warning(f"Unknown scenario: {forecast.scenario}, skipping forecast")
            return
        
        scenario_idx = self.scenario_to_idx[scenario]
        
        # Определяем временной индекс
        time_idx = int(forecast.horizon_minutes / self.time_resolution_minutes)
        if time_idx >= self.time_steps:
            logger.debug(f"Forecast horizon {forecast.horizon_minutes}m exceeds matrix horizon, clamping")
            time_idx = self.time_steps - 1
        
        # Определяем диапазон ценовых индексов
        price_min_idx = self._price_to_index(forecast.price_range['min'])
        price_max_idx = self._price_to_index(forecast.price_range['max'])
        price_target_idx = self._price_to_index(forecast.price_target)
        
        # Проверяем границы
        price_min_idx = max(0, min(price_min_idx, self.price_levels - 1))
        price_max_idx = max(0, min(price_max_idx, self.price_levels - 1))
        price_target_idx = max(0, min(price_target_idx, self.price_levels - 1))
        
        # Вычисляем взвешенную вероятность
        weighted_probability = forecast.confidence * forecast.trust_weight
        
        # Распределяем вероятность по диапазону цен с пиком на целевой цене
        # Используем треугольное распределение
        for price_idx in range(price_min_idx, price_max_idx + 1):
            if price_idx == price_target_idx:
                # Максимум на целевой цене
                prob = weighted_probability
            else:
                # Линейное убывание от целевой цены
                distance = abs(price_idx - price_target_idx)
                max_distance = max(abs(price_max_idx - price_target_idx), 
                                 abs(price_min_idx - price_target_idx))
                if max_distance > 0:
                    prob = weighted_probability * (1.0 - distance / max_distance) * 0.7
                else:
                    prob = weighted_probability * 0.7
            
            # Добавляем к существующей вероятности (накопление)
            self.matrix[time_idx, price_idx, scenario_idx] += prob
        
        self.forecasts_added += 1
        self._cache_valid = False
        
        logger.debug(f"Added forecast: {forecast.analyzer_name}/{forecast.timeframe} -> "
                    f"{scenario.value} @ {forecast.horizon_minutes}m, "
                    f"confidence={forecast.confidence:.2f}, trust={forecast.trust_weight:.2f}")
    
    def apply_blur(self):
        """
        Применяет Gaussian Blur для сглаживания матрицы.
        Создаёт более плавное распределение вероятностей.
        """
        if self.forecasts_added == 0:
            logger.warning("No forecasts added, skipping blur")
            return
        
        # Применяем Gaussian blur по осям времени и цены
        # Не размываем по оси сценариев (они должны оставаться раздельными)
        for scenario_idx in range(self.num_scenarios):
            self.matrix[:, :, scenario_idx] = gaussian_filter(
                self.matrix[:, :, scenario_idx],
                sigma=self.blur_radius,
                mode='constant',
                cval=0.0
            )
        
        # Нормализуем вероятности (чтобы сумма не превышала 1.0 в каждой ячейке)
        max_prob = np.max(self.matrix)
        if max_prob > 1.0:
            self.matrix = self.matrix / max_prob
        
        self.blur_applied = True
        self._cache_valid = False
        
        logger.debug(f"Gaussian blur applied with radius={self.blur_radius}")
    
    def find_max_probability_zones(self, min_probability: Optional[float] = None) -> List[ProbabilityZone]:
        """
        Находит зоны максимальной вероятности в матрице.
        
        Args:
            min_probability: Минимальный порог вероятности (или из конфига)
        
        Returns:
            Список зон, отсортированных по убыванию вероятности
        """
        if self._cache_valid:
            return self._zones_cache
        
        threshold = min_probability or self.min_probability_threshold
        zones = []
        
        # Проходим по всей матрице и ищем локальные максимумы
        for time_idx in range(self.time_steps):
            for scenario_idx in range(self.num_scenarios):
                # Находим локальные максимумы по оси цены
                price_probs = self.matrix[time_idx, :, scenario_idx]
                
                # Простой поиск пиков: точка выше соседей
                for price_idx in range(1, self.price_levels - 1):
                    prob = price_probs[price_idx]
                    
                    if prob < threshold:
                        continue
                    
                    # Проверяем, является ли локальным максимумом
                    if prob > price_probs[price_idx - 1] and prob > price_probs[price_idx + 1]:
                        # Определяем диапазон зоны (где вероятность > 50% от пика)
                        half_prob = prob * 0.5
                        
                        # Ищем границы
                        left_idx = price_idx
                        while left_idx > 0 and price_probs[left_idx] > half_prob:
                            left_idx -= 1
                        
                        right_idx = price_idx
                        while right_idx < self.price_levels - 1 and price_probs[right_idx] > half_prob:
                            right_idx += 1
                        
                        # Создаём зону
                        zone = ProbabilityZone(
                            time_minutes=time_idx * self.time_resolution_minutes,
                            price_center=self._index_to_price(price_idx),
                            price_range=(
                                self._index_to_price(left_idx),
                                self._index_to_price(right_idx)
                            ),
                            scenario=self.idx_to_scenario[scenario_idx],
                            probability=float(prob),
                            contributing_forecasts=1,  # Упрощение, можно улучшить
                            dominant_timeframe="unknown"  # Можно отслеживать при добавлении
                        )
                        zones.append(zone)
        
        # Сортируем по убыванию вероятности
        zones.sort(key=lambda z: z.probability, reverse=True)
        
        # Ограничиваем количество зон
        zones = zones[:self.max_zones_to_return]
        
        # Кэшируем результат
        self._zones_cache = zones
        self._cache_valid = True
        
        logger.info(f"Found {len(zones)} probability zones (threshold={threshold:.2f})")
        
        return zones
    
    def get_forecast_at(self, time_minutes: float, price: float, 
                       scenario: Optional[MarketScenario] = None) -> float:
        """
        Получает вероятность для конкретного времени/цены/сценария.
        
        Args:
            time_minutes: Время в минутах от текущего момента
            price: Уровень цены
            scenario: Сценарий (или None для максимума по всем сценариям)
        
        Returns:
            Вероятность (0.0 - 1.0)
        """
        time_idx = int(time_minutes / self.time_resolution_minutes)
        price_idx = self._price_to_index(price)
        
        # Проверяем границы
        if time_idx < 0 or time_idx >= self.time_steps:
            return 0.0
        if price_idx < 0 or price_idx >= self.price_levels:
            return 0.0
        
        if scenario is None:
            # Возвращаем максимум по всем сценариям
            return float(np.max(self.matrix[time_idx, price_idx, :]))
        else:
            scenario_idx = self.scenario_to_idx[scenario]
            return float(self.matrix[time_idx, price_idx, scenario_idx])
    
    def get_best_scenario_at(self, time_minutes: float, price: float) -> Tuple[MarketScenario, float]:
        """
        Возвращает наиболее вероятный сценарий для времени/цены.
        
        Args:
            time_minutes: Время в минутах от текущего момента
            price: Уровень цены
        
        Returns:
            (сценарий, вероятность)
        """
        time_idx = int(time_minutes / self.time_resolution_minutes)
        price_idx = self._price_to_index(price)
        
        # Проверяем границы
        if time_idx < 0 or time_idx >= self.time_steps:
            return (MarketScenario.FLAT, 0.0)
        if price_idx < 0 or price_idx >= self.price_levels:
            return (MarketScenario.FLAT, 0.0)
        
        # Находим сценарий с максимальной вероятностью
        scenario_probs = self.matrix[time_idx, price_idx, :]
        best_idx = np.argmax(scenario_probs)
        
        return (self.idx_to_scenario[best_idx], float(scenario_probs[best_idx]))
    
    def get_probability_field(self, scenario: Optional[MarketScenario] = None) -> Dict[str, Any]:
        """
        Возвращает поле вероятностей для визуализации/анализа.
        
        Args:
            scenario: Конкретный сценарий или None для всех
        
        Returns:
            Словарь с данными для визуализации
        """
        if scenario is None:
            # Возвращаем данные по всем сценариям
            result = {
                'time_axis': [i * self.time_resolution_minutes for i in range(self.time_steps)],
                'price_axis': [self._index_to_price(i) for i in range(self.price_levels)],
                'scenarios': {}
            }
            
            for scen in MarketScenario:
                scen_idx = self.scenario_to_idx[scen]
                result['scenarios'][scen.value] = self.matrix[:, :, scen_idx].tolist()
            
            return result
        else:
            # Возвращаем данные для конкретного сценария
            scen_idx = self.scenario_to_idx[scenario]
            return {
                'time_axis': [i * self.time_resolution_minutes for i in range(self.time_steps)],
                'price_axis': [self._index_to_price(i) for i in range(self.price_levels)],
                'scenario': scenario.value,
                'probabilities': self.matrix[:, :, scen_idx].tolist()
            }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Возвращает статистику матрицы"""
        return {
            'forecasts_added': self.forecasts_added,
            'blur_applied': self.blur_applied,
            'time_horizon_minutes': self.time_horizon_minutes,
            'time_steps': self.time_steps,
            'price_levels': self.price_levels,
            'price_range': (self.price_min, self.price_max),
            'current_price': self.current_price,
            'max_probability': float(np.max(self.matrix)),
            'mean_probability': float(np.mean(self.matrix[self.matrix > 0])) if np.any(self.matrix > 0) else 0.0,
            'non_zero_cells': int(np.count_nonzero(self.matrix)),
            'total_cells': self.matrix.size
        }
    
    def clear(self):
        """Очистка матрицы для нового цикла"""
        self.matrix.fill(0.0)
        self.forecasts_added = 0
        self.blur_applied = False
        self._cache_valid = False
        self._zones_cache.clear()
        logger.debug("ProbabilityMatrix cleared")
    
    # Вспомогательные методы
    
    def _price_to_index(self, price: float) -> int:
        """Конвертирует цену в индекс массива"""
        if self.price_step == 0:
            return 0
        idx = int((price - self.price_min) / self.price_step)
        return max(0, min(idx, self.price_levels - 1))
    
    def _index_to_price(self, index: int) -> float:
        """Конвертирует индекс массива в цену"""
        return self.price_min + index * self.price_step
