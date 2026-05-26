"""
TENBID v2.0 - Probability Matrix (Матрица Вероятностей)
Центральный модуль принятия решений.
Синтезирует данные от всех анализаторов в многомерное поле вероятностей.
Не говорит "BUY/SELL", а указывает целевые зоны цены и времени.
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import hashlib
import math

logger = logging.getLogger(__name__)

@dataclass
class AnalyzerVector:
    """Вектор данных от отдельного анализатора"""
    analyzer_name: str
    analyzer_type: str  # trend, momentum, volume, news, orderbook, etc.
    
    # Ценовые прогнозы
    target_price: Optional[float] = None
    target_time: Optional[datetime] = None
    
    # Направление и сила
    direction: int = 0  # -1 (down), 0 (neutral), 1 (up)
    strength: float = 0.0  # 0.0 - 1.0
    confidence: float = 0.0  # 0.0 - 1.0
    
    # Уровни поддержки/сопротивления
    support_levels: List[float] = field(default_factory=list)
    resistance_levels: List[float] = field(default_factory=list)
    
    # Дополнительные данные
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    id: str = ""
    
    def __post_init__(self):
        if not self.id:
            data_str = f"{self.analyzer_name}{self.timestamp.isoformat()}{self.target_price}"
            self.id = hashlib.md5(data_str.encode()).hexdigest()[:12]
    
    def to_dict(self) -> Dict:
        return {
            "analyzer_name": self.analyzer_name,
            "analyzer_type": self.analyzer_type,
            "target_price": self.target_price,
            "direction": self.direction,
            "strength": self.strength,
            "confidence": self.confidence,
            "support_levels": self.support_levels,
            "resistance_levels": self.resistance_levels,
            "timestamp": self.timestamp.isoformat(),
            "id": self.id
        }

@dataclass
class ProbabilityZone:
    """Зона вероятности достижения цены"""
    price_low: float
    price_high: float
    probability: float  # 0.0 - 1.0
    expected_time: datetime
    time_window_hours: float
    contributing_analyzers: List[str] = field(default_factory=list)
    confidence: float = 0.0
    zone_type: str = "target"  # target, support, resistance, reversal
    
    @property
    def mid_price(self) -> float:
        return (self.price_low + self.price_high) / 2
    
    @property
    def width_percent(self) -> float:
        if self.mid_price == 0:
            return 0.0
        return (self.price_high - self.price_low) / self.mid_price * 100

@dataclass
class MatrixDecision:
    """Решение матрицы вероятностей"""
    current_price: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Целевые зоны
    bullish_zones: List[ProbabilityZone] = field(default_factory=list)
    bearish_zones: List[ProbabilityZone] = field(default_factory=list)
    
    # Агрегированные показатели
    overall_direction: int = 0  # -1, 0, 1
    overall_confidence: float = 0.0
    market_regime: str = "unknown"  # trending_up, trending_down, ranging, volatile
    
    # Ключевые уровни
    key_support: float = 0.0
    key_resistance: float = 0.0
    
    # Векторы от анализаторов
    analyzer_vectors: List[AnalyzerVector] = field(default_factory=list)
    
    # Метаданные
    id: str = ""
    lineage_snapshot_id: str = ""
    lineage_context_id: str = ""
    
    def __post_init__(self):
        if not self.id:
            data_str = f"{self.timestamp.isoformat()}{self.current_price}{self.overall_direction}"
            self.id = hashlib.md5(data_str.encode()).hexdigest()[:16]
    
    def get_best_zone(self, direction: int) -> Optional[ProbabilityZone]:
        """Получение наилучшей зоны для направления"""
        zones = self.bullish_zones if direction > 0 else self.bearish_zones
        if not zones:
            return None
        
        # Сортировка по вероятности * уверенности
        sorted_zones = sorted(zones, key=lambda z: z.probability * z.confidence, reverse=True)
        return sorted_zones[0]
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "current_price": self.current_price,
            "timestamp": self.timestamp.isoformat(),
            "overall_direction": self.overall_direction,
            "overall_confidence": self.overall_confidence,
            "market_regime": self.market_regime,
            "key_support": self.key_support,
            "key_resistance": self.key_resistance,
            "bullish_zones_count": len(self.bullish_zones),
            "bearish_zones_count": len(self.bearish_zones),
            "analyzer_count": len(self.analyzer_vectors)
        }

class ProbabilityMatrix:
    """
    Матрица вероятностей v2.0.
    Синтезирует векторы от анализаторов, строит поле вероятностей,
    определяет целевые зоны и ключевые уровни.
    """
    
    # Веса по типам анализаторов (настраиваются Автотюнером)
    DEFAULT_WEIGHTS = {
        "trend": 0.20,
        "momentum": 0.15,
        "volume": 0.20,
        "news": 0.10,
        "orderbook": 0.15,
        "fractal": 0.10,
        "multi_tf": 0.10
    }
    
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        Инициализация матрицы.
        
        Args:
            weights: Веса для типов анализаторов
        """
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.vector_cache: List[AnalyzerVector] = []
        self.max_cache_size = 100
        self.last_decision: Optional[MatrixDecision] = None
        
        logger.info(f"ProbabilityMatrix v2.0 инициализирована с весами: {self.weights}")
    
    def update_weights(self, new_weights: Dict[str, float]):
        """Обновление весов от Автотюнера"""
        total = sum(new_weights.values())
        if total > 0:
            # Нормализация весов
            self.weights = {k: v / total for k, v in new_weights.items()}
        else:
            self.weights = new_weights
        
        logger.info(f"Веса матрицы обновлены: {self.weights}")
    
    def add_vector(self, vector: AnalyzerVector):
        """Добавление вектора от анализатора"""
        self.vector_cache.append(vector)
        
        # Очистка старых векторов (старше 1 часа)
        cutoff = datetime.utcnow() - timedelta(hours=1)
        self.vector_cache = [v for v in self.vector_cache if v.timestamp > cutoff]
        
        if len(self.vector_cache) > self.max_cache_size:
            self.vector_cache = self.vector_cache[-self.max_cache_size:]
    
    def synthesize(self, 
                  current_price: float,
                  snapshot_id: str = "",
                  context_id: str = "") -> MatrixDecision:
        """
        Синтез всех векторов в решение матрицы.
        
        Args:
            current_price: Текущая цена актива
            snapshot_id: ID снимка данных (для Data Lineage)
            context_id: ID контекста (для Multi-TF)
            
        Returns:
            MatrixDecision с решением
        """
        if not self.vector_cache:
            logger.warning("Нет векторов для синтеза")
            return MatrixDecision(current_price=current_price)
        
        # Группировка векторов по типам
        vectors_by_type: Dict[str, List[AnalyzerVector]] = {}
        for vector in self.vector_cache:
            if vector.analyzer_type not in vectors_by_type:
                vectors_by_type[vector.analyzer_type] = []
            vectors_by_type[vector.analyzer_type].append(vector)
        
        # Взвешенный расчет направления
        weighted_direction = 0.0
        total_weight = 0.0
        
        for analyzer_type, vectors in vectors_by_type.items():
            type_weight = self.weights.get(analyzer_type, 0.1)
            
            # Средняя уверенность по типу
            avg_confidence = sum(v.confidence for v in vectors) / len(vectors) if vectors else 0
            avg_direction = sum(v.direction * v.strength * v.confidence for v in vectors) / len(vectors) if vectors else 0
            
            weighted_direction += avg_direction * type_weight * avg_confidence
            total_weight += type_weight
        
        if total_weight > 0:
            weighted_direction /= total_weight
        
        # Определение общего направления
        overall_direction = 0
        if weighted_direction > 0.15:
            overall_direction = 1
        elif weighted_direction < -0.15:
            overall_direction = -1
        
        # Расчет общей уверенности
        confidences = [v.confidence for v in self.vector_cache]
        overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        # Построение вероятностных зон
        bullish_zones = self._build_probability_zones(1, current_price)
        bearish_zones = self._build_probability_zones(-1, current_price)
        
        # Определение ключевых уровней
        key_support = self._find_key_level(current_price, direction=-1)
        key_resistance = self._find_key_level(current_price, direction=1)
        
        # Определение режима рынка
        market_regime = self._determine_market_regime(bullish_zones, bearish_zones, overall_confidence)
        
        decision = MatrixDecision(
            current_price=current_price,
            bullish_zones=bullish_zones,
            bearish_zones=bearish_zones,
            overall_direction=overall_direction,
            overall_confidence=overall_confidence,
            market_regime=market_regime,
            key_support=key_support,
            key_resistance=key_resistance,
            analyzer_vectors=self.vector_cache.copy(),
            lineage_snapshot_id=snapshot_id,
            lineage_context_id=context_id
        )
        
        self.last_decision = decision
        
        logger.info(f"MatrixDecision: Direction={decision.overall_direction}, Confidence={decision.overall_confidence:.2f}, Regime={decision.market_regime}")
        
        return decision
    
    def _build_probability_zones(self, direction: int, current_price: float) -> List[ProbabilityZone]:
        """Построение вероятностных зон для направления"""
        zones = []
        
        # Фильтрация векторов по направлению
        relevant_vectors = [
            v for v in self.vector_cache 
            if v.direction == direction and v.target_price is not None
        ]
        
        if not relevant_vectors:
            return zones
        
        # Кластеризация целевых цен
        target_prices = [v.target_price for v in relevant_vectors]
        confidences = [v.confidence * v.strength for v in relevant_vectors]
        
        # Простая кластеризация: группировка близких цен
        target_prices_sorted = sorted(target_prices)
        clusters = []
        current_cluster = [target_prices_sorted[0]]
        
        for i in range(1, len(target_prices_sorted)):
            if abs(target_prices_sorted[i] - target_prices_sorted[i-1]) < current_price * 0.01:  # 1% порог
                current_cluster.append(target_prices_sorted[i])
            else:
                clusters.append(current_cluster)
                current_cluster = [target_prices_sorted[i]]
        
        clusters.append(current_cluster)
        
        # Создание зон из кластеров
        for cluster in clusters:
            if not cluster:
                continue
            
            price_low = min(cluster)
            price_high = max(cluster)
            mid_price = (price_low + price_high) / 2
            
            # Расчет вероятности на основе количества векторов и их уверенности
            cluster_vectors = [v for v in relevant_vectors if price_low <= v.target_price <= price_high]
            avg_confidence = sum(v.confidence for v in cluster_vectors) / len(cluster_vectors)
            probability = min(1.0, len(cluster_vectors) / 5.0 * avg_confidence)
            
            # Оценка времени достижения (упрощенно)
            price_distance = abs(mid_price - current_price) / current_price
            expected_hours = price_distance * 24  # 1% цены = 24 часа (настраиваемо)
            
            zone = ProbabilityZone(
                price_low=price_low,
                price_high=price_high,
                probability=probability,
                expected_time=datetime.utcnow() + timedelta(hours=expected_hours),
                time_window_hours=max(1.0, expected_hours * 0.5),
                contributing_analyzers=list(set(v.analyzer_name for v in cluster_vectors)),
                confidence=avg_confidence,
                zone_type="target" if direction > 0 else "target"
            )
            
            zones.append(zone)
        
        # Сортировка по вероятности
        zones.sort(key=lambda z: z.probability, reverse=True)
        
        return zones
    
    def _find_key_level(self, current_price: float, direction: int) -> float:
        """Поиск ключевого уровня поддержки или сопротивления"""
        all_levels = []
        
        for vector in self.vector_cache:
            if direction < 0:  # Поддержка
                all_levels.extend(vector.support_levels)
            else:  # Сопротивление
                all_levels.extend(vector.resistance_levels)
        
        if not all_levels:
            return 0.0
        
        # Фильтрация уровней по направлению
        if direction < 0:
            relevant_levels = [l for l in all_levels if l < current_price]
        else:
            relevant_levels = [l for l in all_levels if l > current_price]
        
        if not relevant_levels:
            return 0.0
        
        # Возврат ближайшего уровня
        if direction < 0:
            return max(relevant_levels)
        else:
            return min(relevant_levels)
    
    def _determine_market_regime(self, 
                                bullish_zones: List[ProbabilityZone],
                                bearish_zones: List[ProbabilityZone],
                                confidence: float) -> str:
        """Определение режима рынка"""
        if confidence < 0.3:
            return "ranging"
        
        bull_strength = sum(z.probability * z.confidence for z in bullish_zones)
        bear_strength = sum(z.probability * z.confidence for z in bearish_zones)
        
        if bull_strength > bear_strength * 1.5:
            return "trending_up"
        elif bear_strength > bull_strength * 1.5:
            return "trending_down"
        elif bull_strength > 0.5 or bear_strength > 0.5:
            return "volatile"
        else:
            return "ranging"
    
    def get_reversal_probability(self, current_price: float) -> float:
        """
        Расчет вероятности разворота.
        Используется Execution модулем для стратегии противохода.
        """
        if not self.last_decision:
            return 0.0
        
        # Проверка близости к ключевым уровням
        distance_to_support = (current_price - self.last_decision.key_support) / current_price if self.last_decision.key_support > 0 else 1.0
        distance_to_resistance = (self.last_decision.key_resistance - current_price) / current_price if self.last_decision.key_resistance > 0 else 1.0
        
        # Высокая вероятность разворота near ключевых уровней
        reversal_prob = 0.0
        
        if distance_to_support < 0.02:  # Близко к поддержке
            reversal_prob = max(reversal_prob, 0.7 * (1.0 - distance_to_support / 0.02))
        
        if distance_to_resistance < 0.02:  # Близко к сопротивлению
            reversal_prob = max(reversal_prob, 0.7 * (1.0 - distance_to_resistance / 0.02))
        
        # Учет противоположных зон
        if self.last_decision.overall_direction > 0 and self.last_decision.bearish_zones:
            reversal_prob = max(reversal_prob, max(z.probability for z in self.last_decision.bearish_zones) * 0.5)
        elif self.last_decision.overall_direction < 0 and self.last_decision.bullish_zones:
            reversal_prob = max(reversal_prob, max(z.probability for z in self.last_decision.bullish_zones) * 0.5)
        
        return min(1.0, reversal_prob)
    
    def clear_cache(self):
        """Очистка кэша векторов"""
        self.vector_cache.clear()
        logger.info("Кэш векторов матрицы очищен")
