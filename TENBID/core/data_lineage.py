"""
Система маркировки данных (Data Lineage) для TENBID.

Этот модуль обеспечивает отслеживание происхождения всех данных,
используемых в аналитике и торговле. Каждый результат анализа
содержит метаданные о том, какие данные были использованы,
с каким качеством и надежностью.

Это позволяет:
- Shadow анализатору понимать зависимость результатов от входных данных
- Autotuner'у оценивать качество данных и корректировать веса
- Системе управления рисками адаптировать параметры сделки
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
import hashlib


class DataSource(Enum):
    """Источники данных"""
    BINANCE_API = "binance_api"
    BINANCE_WEBSOCKET = "binance_websocket"
    SYNTHETIC_TF = "synthetic_timeframe"
    CALCULATED = "calculated"
    EXTERNAL = "external"
    USER_INPUT = "user_input"


class DataQuality(Enum):
    """Качество данных"""
    HIGH = 1.0      # Прямые данные с API, свежие
    MEDIUM = 0.7    # Синтетические ТФ, расчетные данные
    LOW = 0.4       # Старые данные, экстраполяция
    VERY_LOW = 0.2  # Заглушки, предположения


@dataclass
class DataLineage:
    """
    Информация о происхождении данных.
    
    Атрибуты:
        source: Источник данных (API, расчет, синтетика)
        quality: Качество данных (0.0-1.0)
        timestamp: Время получения/создания данных
        age_seconds: Возраст данных в секундах
        dependencies: Список зависимых DataLineage (откуда получены эти данные)
        calculation_method: Метод расчета (если применимо)
        confidence: Уверенность в данных (0.0-1.0)
        metadata: Дополнительные метаданные
    """
    source: DataSource
    quality: DataQuality
    timestamp: datetime
    age_seconds: float = 0.0
    dependencies: List['DataLineage'] = field(default_factory=list)
    calculation_method: Optional[str] = None
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Вычисление возраста и обновление confidence"""
        if self.age_seconds == 0.0:
            delta = datetime.now() - self.timestamp
            self.age_seconds = delta.total_seconds()
        
        # Confidence зависит от качества и возраста
        time_decay = max(0.0, 1.0 - (self.age_seconds / 3600))  # Деградация за 1 час
        self.confidence = self.quality.value * time_decay
    
    def get_lineage_tree(self, depth: int = 0) -> str:
        """Возвращает дерево зависимостей в виде строки"""
        indent = "  " * depth
        result = f"{indent}├─ {self.source.value} (q={self.quality.value:.2f}, c={self.confidence:.2f})"
        if self.calculation_method:
            result += f" [{self.calculation_method}]"
        result += "\n"
        
        for dep in self.dependencies:
            result += dep.get_lineage_tree(depth + 1)
        
        return result
    
    def to_dict(self) -> Dict:
        """Сериализация в словарь для БД/логов"""
        return {
            'source': self.source.value,
            'quality': self.quality.value,
            'timestamp': self.timestamp.isoformat(),
            'age_seconds': self.age_seconds,
            'calculation_method': self.calculation_method,
            'confidence': self.confidence,
            'metadata': self.metadata,
            'dependencies_count': len(self.dependencies)
        }


@dataclass
class AnalysisContext:
    """
    Контекст анализа, содержащий результаты и их происхождение.
    
    Это основной контейнер, который передается между модулями.
    Каждый модуль добавляет свои результаты с соответствующей маркировкой.
    
    Атрибуты:
        symbol: Торговая пара (например, ETHUSDT)
        timeframe: Таймфрейм анализа
        timestamp: Время создания контекста
        data_lineage: Маркировка исходных данных
        results: Результаты анализов (ключ -> значение)
        lineage_map: Маркировка для каждого результата (ключ -> DataLineage)
        scores: Оценки доверия для различных компонентов
        metadata: Дополнительные метаданные
    """
    symbol: str
    timeframe: str
    timestamp: datetime = field(default_factory=datetime.now)
    data_lineage: Optional[DataLineage] = None
    results: Dict[str, Any] = field(default_factory=dict)
    lineage_map: Dict[str, DataLineage] = field(default_factory=dict)
    scores: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_result(self, key: str, value: Any, lineage: DataLineage):
        """
        Добавить результат анализа с маркировкой.
        
        Args:
            key: Идентификатор результата (например, 'trend_direction')
            value: Значение результата
            lineage: Информация о происхождении данных
        """
        self.results[key] = value
        self.lineage_map[key] = lineage
        
        # Логирование добавления результата (опционально)
        # logger.debug(f"Added result '{key}' with lineage from {lineage.source.value}")
    
    def add_score(self, key: str, score: float, lineage: Optional[DataLineage] = None):
        """
        Добавить оценку доверия.
        
        Args:
            key: Идентификатор оценки (например, 'trend_confidence')
            score: Значение оценки (0.0-1.0)
            lineage: Опциональная маркировка источника оценки
        """
        self.scores[key] = score
        if lineage:
            self.lineage_map[f"score_{key}"] = lineage
    
    def get_result_with_lineage(self, key: str) -> tuple:
        """
        Получить результат и его маркировку.
        
        Returns:
            Кортеж (значение, DataLineage) или (None, None) если ключ не найден
        """
        value = self.results.get(key)
        lineage = self.lineage_map.get(key)
        return value, lineage
    
    def get_average_confidence(self) -> float:
        """Средняя уверенность по всем результатам"""
        if not self.lineage_map:
            return 0.0
        
        confidences = [lg.confidence for lg in self.lineage_map.values()]
        return sum(confidences) / len(confidences)
    
    def get_min_confidence(self) -> float:
        """Минимальная уверенность (слабое звено)"""
        if not self.lineage_map:
            return 0.0
        
        return min(lg.confidence for lg in self.lineage_map.values())
    
    def get_lineage_summary(self) -> str:
        """Краткая сводка по всем источникам данных"""
        if not self.data_lineage:
            return "No root lineage"
        
        summary = f"Root: {self.data_lineage.source.value} (c={self.data_lineage.confidence:.2f})\n"
        summary += f"Results: {len(self.results)}, Avg confidence: {self.get_average_confidence():.2f}\n"
        summary += f"Min confidence: {self.get_min_confidence():.2f}"
        
        return summary
    
    def to_dict(self) -> Dict:
        """Сериализация в словарь для БД/логов"""
        return {
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'timestamp': self.timestamp.isoformat(),
            'data_lineage': self.data_lineage.to_dict() if self.data_lineage else None,
            'results_count': len(self.results),
            'scores': self.scores,
            'avg_confidence': self.get_average_confidence(),
            'min_confidence': self.get_min_confidence(),
            'metadata': self.metadata
        }
    
    def create_child(self, timeframe: Optional[str] = None) -> 'AnalysisContext':
        """
        Создать дочерний контекст для другого ТФ или анализа.
        Наследует маркировку корневых данных.
        """
        child = AnalysisContext(
            symbol=self.symbol,
            timeframe=timeframe or self.timeframe,
            data_lineage=self.data_lineage,
            metadata={**self.metadata, 'parent_tf': self.timeframe}
        )
        return child


class LineageTracker:
    """
    Трекер для создания и управления маркировками.
    
    Упрощает создание DataLineage с правильными зависимостями.
    """
    
    @staticmethod
    def create_from_source(
        source: DataSource,
        quality: DataQuality,
        metadata: Optional[Dict] = None
    ) -> DataLineage:
        """Создать маркировку для данных из источника"""
        return DataLineage(
            source=source,
            quality=quality,
            timestamp=datetime.now(),
            metadata=metadata or {}
        )
    
    @staticmethod
    def create_calculated(
        method: str,
        dependencies: List[DataLineage],
        quality: DataQuality = DataQuality.MEDIUM,
        metadata: Optional[Dict] = None
    ) -> DataLineage:
        """
        Создать маркировку для расчетных данных.
        
        Args:
            method: Название метода расчета
            dependencies: От каких данных зависит результат
            quality: Качество результата (по умолчанию MEDIUM)
            metadata: Дополнительные метаданные
        """
        lineage = DataLineage(
            source=DataSource.CALCULATED,
            quality=quality,
            timestamp=datetime.now(),
            dependencies=dependencies,
            calculation_method=method,
            metadata=metadata or {}
        )
        return lineage
    
    @staticmethod
    def merge_lineages(lineages: List[DataLineage], method: str) -> DataLineage:
        """
        Объединить несколько маркировок в одну.
        Используется когда результат зависит от нескольких источников.
        """
        if not lineages:
            raise ValueError("Нельзя объединить пустой список маркировок")
        
        # Средняя kualitas зависит от всех зависимостей
        avg_quality = sum(lg.quality.value for lg in lineages) / len(lineages)
        quality = DataQuality(min(1.0, avg_quality + 0.1))  # Небольшой бонус за агрегацию
        
        return DataLineage(
            source=DataSource.CALCULATED,
            quality=quality,
            timestamp=datetime.now(),
            dependencies=lineages,
            calculation_method=method,
            metadata={'merged_count': len(lineages)}
        )


# Пример использования
if __name__ == "__main__":
    # Создание корневого контекста
    ctx = AnalysisContext(symbol="ETHUSDT", timeframe="5m")
    
    # Создание маркировки для сырых данных
    root_lineage = LineageTracker.create_from_source(
        source=DataSource.BINANCE_API,
        quality=DataQuality.HIGH,
        metadata={'candles_count': 100}
    )
    ctx.data_lineage = root_lineage
    
    # Добавление результата с маркировкой
    trend_lineage = LineageTracker.create_calculated(
        method="MA_crossover",
        dependencies=[root_lineage],
        quality=DataQuality.MEDIUM
    )
    ctx.add_result('trend_direction', 'UP', trend_lineage)
    ctx.add_score('trend_confidence', 0.85, trend_lineage)
    
    # Вывод информации
    print(ctx.get_lineage_summary())
    print("\nLineage tree:")
    print(trend_lineage.get_lineage_tree())
    print("\nSerialized:")
    print(ctx.to_dict())
