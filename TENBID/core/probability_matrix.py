"""
Ядро системы вероятностного моделирования.
Строит многомерную матрицу вероятностей (Время, Цена, Сценарий) -> Вероятность.
Заменяет упрощенный расчет confidence.
"""
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class MarketScenario(Enum):
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    FLAT = "flat"
    BREAKOUT_UP = "breakout_up"
    BREAKOUT_DOWN = "breakout_down"

@dataclass
class ProbabilityCell:
    """Ячейка матрицы вероятностей."""
    timestamp: float
    price_level: float
    scenario: MarketScenario
    probability: float  # 0.0 - 1.0
    confidence_source: str  # Идентификатор источника данных
    context_profile_id: str  # ID контекстного профиля

class ProbabilityMatrix:
    def __init__(self, time_horizon_minutes: int = 60, price_levels_count: int = 50):
        self.time_horizon = time_horizon_minutes
        self.price_levels_count = price_levels_count
        self.matrix: Dict[Tuple[float, float, MarketScenario], ProbabilityCell] = {}
        self.base_price = 0.0
        self.time_step = 5  # минут
        self.price_step = 0.0  # Будет рассчитан динамически
        
    def initialize(self, current_price: float, volatility: float):
        """Инициализация матрицы вокруг текущей цены."""
        self.base_price = current_price
        # Динамический шаг цены на основе волатильности
        self.price_step = volatility * 0.01 if volatility > 0 else current_price * 0.001
        
        logger.info(f"ProbabilityMatrix initialized: base_price={current_price}, step={self.price_step}")
        
    def update_probability(self, timestamp: float, price_level: float, scenario: MarketScenario, 
                          probability: float, source_id: str, context_id: str):
        """Обновление вероятности для конкретной ячейки."""
        key = (timestamp, price_level, scenario)
        
        if key in self.matrix:
            # Усреднение с учетом веса источника (можно улучшить)
            cell = self.matrix[key]
            cell.probability = (cell.probability + probability) / 2.0
        else:
            self.matrix[key] = ProbabilityCell(
                timestamp=timestamp,
                price_level=price_level,
                scenario=scenario,
                probability=probability,
                confidence_source=source_id,
                context_profile_id=context_id
            )
            
    def get_best_scenario(self, future_time: float) -> Optional[Tuple[MarketScenario, float, float]]:
        """Возвращает наиболее вероятный сценарий для указанного времени."""
        best_prob = 0.0
        best_scenario = None
        best_price = None
        
        for (ts, price, scenario), cell in self.matrix.items():
            if abs(ts - future_time) < self.time_step:  # Попадание в временное окно
                if cell.probability > best_prob:
                    best_prob = cell.probability
                    best_scenario = scenario
                    best_price = price
                    
        return (best_scenario, best_price, best_prob) if best_scenario else None
    
    def get_probability_field(self) -> Dict[str, List[Dict]]:
        """Возвращает всё поле вероятностей для визуализации/анализа."""
        result = {}
        for scenario in MarketScenario:
            result[scenario.value] = []
            
        for (ts, price, scenario), cell in self.matrix.items():
            result[scenario.value].append({
                'time': ts,
                'price': price,
                'probability': cell.probability,
                'source': cell.confidence_source,
                'context': cell.context_profile_id
            })
            
        return result
    
    def clear(self):
        """Очистка матрицы для нового цикла."""
        self.matrix.clear()
        logger.debug("ProbabilityMatrix cleared")
