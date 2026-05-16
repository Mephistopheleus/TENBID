import logging
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

logger = logging.getLogger(__name__)

class DataQuality(Enum):
    LOW = 0.5
    MEDIUM = 0.8
    HIGH = 1.0
    EXCELLENT = 1.2

class ConfidenceSystem:
    def __init__(self):
        # Базовые веса могут быть переопределены извне (от Autotuner)
        self.default_weights = {
            "rsi": 1.0,
            "macd": 1.0,
            "bb": 1.0,
            "volatility": 1.0,
            "fractal": 1.0,
            "regime": 1.0,
            "volume": 1.0,
            "orderbook": 1.0
        }
        logger.info("ConfidenceSystem initialized")

    def calculate(self, signals: Dict[str, Any], weights_override: Optional[Dict[str, float]] = None, 
                  data_lineage: Optional[Dict[str, DataQuality]] = None) -> Tuple[float, Dict[str, Any]]:
        """
        Рассчитывает итоговый confidence score.
        :param signals: Словарь сигналов от индикаторов (значение от -1 до 1 или 0/1)
        :param weights_override: Внешние веса от Autotuner (приоритет над дефолтными)
        :param data_lineage: Информация о качестве данных
        :return: (confidence_score, details)
        """
        weights = {**self.default_weights, **(weights_override or {})}
        lineage = data_lineage or {}
        
        total_score = 0.0
        total_weight = 0.0
        breakdown = {}

        # Список ожидаемых индикаторов
        indicators = ["rsi", "macd", "bb", "volatility", "fractal", "regime", "volume", "orderbook"]

        for ind in indicators:
            if ind not in signals:
                continue
            
            signal_val = signals[ind]
            # Нормализация сигнала к диапазону [0, 1] для удобства, если нужно
            # Сейчас предполагаем, что сигнал уже готов к взвешиванию или это бинарный флаг
            
            w = weights.get(ind, 1.0)
            
            # Применение множителя качества данных (Data Lineage)
            quality_mult = 1.0
            if ind in lineage:
                quality_mult = lineage[ind].value
            
            final_weight = w * quality_mult
            
            # Взвешенный вклад сигнала
            # Пример логики: если сигнал сильный (близок к 1 или -1), он вносит больший вклад
            contribution = signal_val * final_weight
            
            total_score += contribution
            total_weight += final_weight
            
            breakdown[ind] = {
                "signal": signal_val,
                "weight": w,
                "quality_mult": quality_mult,
                "final_weight": final_weight,
                "contribution": contribution
            }

        if total_weight == 0:
            return 0.0, {"error": "No valid signals"}

        # Нормализация итогового скоринга (примерная)
        # Если сумма вкладов положительная и большая, confidence растет
        raw_score = total_score / total_weight
        
        # Преобразование в диапазон [0, 1] через сигмоиду или простое масштабирование
        # Допустим, raw_score может быть от -1 до 1. 
        # Конвертируем: (raw_score + 1) / 2 -> [0, 1]
        confidence = (raw_score + 1.0) / 2.0
        
        # Ограничение [0, 1]
        confidence = max(0.0, min(1.0, confidence))

        details = {
            "raw_score": raw_score,
            "total_weight": total_weight,
            "breakdown": breakdown,
            "quality_applied": len(lineage) > 0
        }

        return confidence, details
