"""
TENBID v2.0 - Volume Profile Analyzer
Анализ распределения объемов по ценовым уровням.
Выявляет ключевые зоны ликвидности (POC, Value Area).
Работает в синергии со стаканом для точного прогнозирования.
Интегрирован с DataLineage v2.0.
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
import logging
import hashlib
import math
from core.data_lineage import DataLineageManager

logger = logging.getLogger(__name__)

@dataclass
class VolumeNode:
    """Узел объема на определенном ценовом уровне"""
    price: float
    volume: float
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    trade_count: int = 0
    
    @property
    def total_volume(self) -> float:
        return self.volume
    
    @property
    def imbalance(self) -> float:
        """Дисбаланс между покупками и продажами"""
        if self.volume == 0:
            return 0.0
        return (self.buy_volume - self.sell_volume) / self.volume

@dataclass
class VolumeProfileResult:
    """Результат анализа объемного профиля (внутренний контейнер)"""
    poc_price: float = 0.0
    poc_volume: float = 0.0
    value_area_high: float = 0.0
    value_area_low: float = 0.0
    value_area_volume: float = 0.0
    total_volume: float = 0.0
    nodes: List[VolumeNode] = field(default_factory=list)
    profile_type: str = "balanced"
    confidence: float = 0.0
    imbalance_ratio: float = 1.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    id: str = ""
    
    def __post_init__(self):
        if not self.id:
            self.id = hashlib.md5(f"{self.timestamp.isoformat()}{self.poc_price}".encode()).hexdigest()[:12]
    
    def to_dict(self) -> Dict:
        return {
            "poc_price": self.poc_price,
            "value_area_high": self.value_area_high,
            "value_area_low": self.value_area_low,
            "profile_type": self.profile_type,
            "confidence": self.confidence,
            "total_volume": self.total_volume,
            "imbalance_ratio": self.imbalance_ratio,
            "timestamp": self.timestamp.isoformat(),
            "id": self.id
        }

class VolumeProfileAnalyzer:
    """
    Анализатор объемного профиля.
    Строит распределение объемов по ценовым уровням,
    выявляет ключевые зоны поддержки/сопротивления.
    Интегрирован с DataLineageManager v2.0.
    """
    
    VALUE_AREA_PERCENT = 0.70
    
    def __init__(self, lineage_manager: DataLineageManager, price_precision: int = 2, volume_buckets: int = 50):
        """
        Инициализация анализатора.
        
        Args:
            lineage_manager: Менеджер линейности данных (v2.0)
            price_precision: Точность цены для группировки
            volume_buckets: Количество ценовых уровней (корзин)
        """
        self.lineage_manager = lineage_manager
        self.price_precision = price_precision
        self.volume_buckets = volume_buckets
        logger.info(f"VolumeProfileAnalyzer инициализирован (buckets={volume_buckets})")
    
    def analyze_candles(self, 
                       snapshot_id: str,
                       candles: List[Dict], 
                       symbol: str,
                       timeframe: str = "5m") -> Dict[str, Any]:
        """
        Анализ свечных данных для построения объемного профиля.
        Создает узел анализа в графе данных.
        
        Args:
            snapshot_id: ID родительского снимка рынка
            candles: Список свечей с полями: open, high, low, close, volume
            symbol: Тикер актива
            timeframe: Таймфрейм свечей
            
        Returns:
            Словарь с результатами анализа и node_id
        """
        if not candles or len(candles) < 2:
            logger.warning(f"Недостаточно данных для анализа объема ({symbol} {timeframe})")
            return {
                'status': 'error',
                'node_id': None,
                'error': 'Insufficient data',
                'poc': None,
                'vah': None,
                'val': None
            }
        
        try:
            # Определение диапазона цен
            all_prices = []
            for candle in candles:
                all_prices.extend([candle['low'], candle['high']])
            
            min_price = min(all_prices)
            max_price = max(all_prices)
            
            if min_price == max_price:
                return {
                    'status': 'error',
                    'node_id': None,
                    'error': 'Zero price range',
                    'poc': None,
                    'vah': None,
                    'val': None
                }
            
            # Создание ценовых корзин
            step = (max_price - min_price) / self.volume_buckets
            buckets: Dict[float, VolumeNode] = {}
            
            for i in range(self.volume_buckets):
                bucket_price = round(min_price + i * step, self.price_precision)
                buckets[bucket_price] = VolumeNode(price=bucket_price, volume=0.0)
            
            # Распределение объемов по корзинам
            total_volume = 0.0
            for candle in candles:
                close_price = candle['close']
                volume = candle.get('volume', 0)
                
                # Нахождение ближайшей корзины
                bucket_idx = int((close_price - min_price) / step)
                bucket_idx = min(bucket_idx, self.volume_buckets - 1)
                bucket_price = round(min_price + bucket_idx * step, self.price_precision)
                
                if bucket_price in buckets:
                    buckets[bucket_price].volume += volume
                    buckets[bucket_price].trade_count += 1
                    
                    # Оценка buy/sell объема
                    if candle['close'] >= candle['open']:
                        buckets[bucket_price].buy_volume += volume
                    else:
                        buckets[bucket_price].sell_volume += volume
                
                total_volume += volume
            
            # Конвертация в список
            nodes = [node for node in buckets.values() if node.volume > 0]
            nodes.sort(key=lambda x: x.price)
            
            if not nodes:
                return {
                    'status': 'error',
                    'node_id': None,
                    'error': 'No volume nodes',
                    'poc': None,
                    'vah': None,
                    'val': None
                }
            
            # Поиск POC (Point of Control)
            poc_node = max(nodes, key=lambda x: x.volume)
            
            # Расчет области ценности (Value Area)
            target_volume = total_volume * self.VALUE_AREA_PERCENT
            sorted_by_volume = sorted(nodes, key=lambda x: x.volume, reverse=True)
            
            va_nodes = []
            accumulated_volume = 0.0
            
            for node in sorted_by_volume:
                va_nodes.append(node)
                accumulated_volume += node.volume
                if accumulated_volume >= target_volume:
                    break
            
            # Границы области ценности
            va_prices = [node.price for node in va_nodes]
            va_low = min(va_prices)
            va_high = max(va_prices)
            va_volume = accumulated_volume
            
            # Определение типа профиля
            profile_type = self._classify_profile(nodes, poc_node, va_low, va_high, min_price, max_price)
            
            # Расчет уверенности
            confidence = self._calculate_confidence(nodes, total_volume, poc_node.volume, va_high, va_low, max_price, min_price)
            
            # Расчет дисбаланса
            vol_above = sum(n.buy_volume for n in nodes if n.price > poc_node.price) + sum(n.sell_volume for n in nodes if n.price > poc_node.price) # Упрощенно
            vol_below = sum(n.buy_volume for n in nodes if n.price < poc_node.price) + sum(n.sell_volume for n in nodes if n.price < poc_node.price)
            
            # Более точный расчет дисбаланса на основе buy/sell volumes
            total_buy_above = sum(n.buy_volume for n in nodes if n.price > poc_node.price)
            total_sell_above = sum(n.sell_volume for n in nodes if n.price > poc_node.price)
            total_buy_below = sum(n.buy_volume for n in nodes if n.price < poc_node.price)
            total_sell_below = sum(n.sell_volume for n in nodes if n.price < poc_node.price)
            
            # Imbalance ratio: (Buy Above + Sell Below) / (Sell Above + Buy Below) - логика накопления/распределения
            # Упрощенно: отношение объема выше POC к объему ниже
            vol_above_simple = sum(n.volume for n in nodes if n.price > poc_node.price)
            vol_below_simple = sum(n.volume for n in nodes if n.price < poc_node.price)
            
            if vol_below_simple == 0:
                imbalance_ratio = 999.0 if vol_above_simple > 0 else 1.0
            else:
                imbalance_ratio = vol_above_simple / vol_below_simple

            # Формирование внутреннего объекта результата
            result_obj = VolumeProfileResult(
                poc_price=poc_node.price,
                poc_volume=poc_node.volume,
                value_area_high=va_high,
                value_area_low=va_low,
                value_area_volume=va_volume,
                total_volume=total_volume,
                nodes=nodes,
                profile_type=profile_type,
                confidence=confidence,
                imbalance_ratio=imbalance_ratio
            )
            
            # Создание узла Lineage (v2.0)
            analysis_vector = {
                'poc': result_obj.poc_price,
                'vah': result_obj.value_area_high,
                'val': result_obj.value_area_low,
                'va_volume': result_obj.value_area_volume,
                'type': result_obj.profile_type,
                'imbalance': result_obj.imbalance_ratio,
                'total_vol': result_obj.total_volume
            }
            
            node_id = self.lineage_manager.create_analysis_node(
                parent_snapshot_id=snapshot_id,
                analyzer_name=f"volume_profile_{timeframe}",
                result_vector=analysis_vector,
                confidence=result_obj.confidence,
                additional_meta={
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'buckets_count': len(nodes),
                    'calculation_method': 'close_price_bucketing'
                }
            )
            
            # Возврат словаря
            return {
                'status': 'success',
                'node_id': node_id,
                'poc': result_obj.poc_price,
                'vah': result_obj.value_area_high,
                'val': result_obj.value_area_low,
                'width': result_obj.value_area_high - result_obj.value_area_low,
                'type': result_obj.profile_type,
                'confidence': result_obj.confidence,
                'imbalance_ratio': result_obj.imbalance_ratio,
                'total_volume': result_obj.total_volume,
                'details': f"Profile {result_obj.profile_type} formed with POC at {result_obj.poc_price}"
            }
            
        except Exception as e:
            logger.error(f"Ошибка при анализе Volume Profile ({symbol} {timeframe}): {e}", exc_info=True)
            return {
                'status': 'error',
                'node_id': None,
                'error_message': str(e),
                'poc': None,
                'vah': None,
                'val': None
            }
    
    def _classify_profile(self, 
                         nodes: List[VolumeNode], 
                         poc: VolumeNode,
                         va_low: float, 
                         va_high: float,
                         min_price: float,
                         max_price: float) -> str:
        """Классификация типа профиля"""
        if not nodes:
            return "unknown"
        
        price_range = max_price - min_price
        
        if price_range == 0:
            return "flat"
        
        # Позиция POC относительно диапазона
        poc_position = (poc.price - min_price) / price_range
        
        # Ширина области ценности
        va_width = va_high - va_low
        va_relative_width = va_width / price_range if price_range > 0 else 0
        
        if poc_position > 0.7:
            return "bearish"  # POC в верхней части - медвежий профиль
        elif poc_position < 0.3:
            return "bullish"  # POC в нижней части - бычий профиль
        elif va_relative_width < 0.4:
            return "narrow"   # Узкая область ценности - консолидация
        else:
            return "balanced" # Сбалансированный профиль
    
    def _calculate_confidence(self, 
                             nodes: List[VolumeNode], 
                             total_volume: float, 
                             poc_volume: float,
                             va_high: float,
                             va_low: float,
                             max_price: float,
                             min_price: float) -> float:
        """Расчет уверенности в профиле"""
        if not nodes or total_volume == 0:
            return 0.0
        
        # Уверенность растет с количеством данных и концентрацией объема в POC
        data_factor = min(1.0, len(nodes) / 20.0)  # Нормализация по количеству узлов
        concentration_factor = poc_volume / total_volume if total_volume > 0 else 0
        
        # Штраф за слишком широкую зону стоимости
        price_range = max_price - min_price
        width_penalty = 1.0
        if price_range > 0:
            relative_width = (va_high - va_low) / price_range
            if relative_width > 0.8:
                width_penalty = 0.6
            elif relative_width < 0.2:
                width_penalty = 0.8
            else:
                width_penalty = 1.0
        
        # Нормализация концентрации
        norm_concentration = min(1.0, math.log(concentration_factor * 20 + 1) / math.log(21))
        
        confidence = (data_factor * 0.4 + norm_concentration * 0.6) * width_penalty
        
        return max(0.1, min(1.0, confidence))
    
    def get_support_resistance_levels(self, 
                                     profile: VolumeProfileResult,
                                     additional_profiles: Optional[List[VolumeProfileResult]] = None) -> List[Dict]:
        """
        Вычисление уровней поддержки и сопротивления на основе профиля.
        
        Args:
            profile: Текущий профиль объема
            additional_profiles: Дополнительные профили (старшие ТФ)
            
        Returns:
            Список уровней с типом и силой
        """
        levels = []
        
        if profile.poc_price > 0:
            levels.append({
                "price": profile.poc_price,
                "type": "POC",
                "strength": profile.confidence,
                "description": "Point of Control - максимальный объем"
            })
        
        if profile.value_area_high > 0:
            levels.append({
                "price": profile.value_area_high,
                "type": "VAH",
                "strength": profile.confidence * 0.8,
                "description": "Value Area High - верхняя граница"
            })
        
        if profile.value_area_low > 0:
            levels.append({
                "price": profile.value_area_low,
                "type": "VAL",
                "strength": profile.confidence * 0.8,
                "description": "Value Area Low - нижняя граница"
            })
        
        # Объединение с дополнительными профилями
        if additional_profiles:
            for add_profile in additional_profiles:
                if add_profile.poc_price > 0 and add_profile.poc_price != profile.poc_price:
                    levels.append({
                        "price": add_profile.poc_price,
                        "type": "POC_HTF",
                        "strength": add_profile.confidence * 0.9,  # Старшие ТФ имеют больший вес
                        "description": "POC старшего таймфрейма"
                    })
        
        # Сортировка по силе
        levels.sort(key=lambda x: x["strength"], reverse=True)
        
        return levels
    
    def merge_profiles(self, profiles: List[VolumeProfileResult]) -> VolumeProfileResult:
        """
        Объединение нескольких профилей (для мульти-ТФ анализа).
        
        Args:
            profiles: Список профилей для объединения
            
        Returns:
            Объединенный профиль
        """
        if not profiles:
            return VolumeProfileResult()
        
        if len(profiles) == 1:
            return profiles[0]
        
        # Взвешенное объединение POC
        total_weight = sum(p.confidence for p in profiles)
        if total_weight == 0:
            return profiles[0]
        
        weighted_poc = sum(p.poc_price * p.confidence for p in profiles) / total_weight
        
        # Объединение областей ценности
        all_va_lows = [p.value_area_low for p in profiles if p.value_area_low > 0]
        all_va_highs = [p.value_area_high for p in profiles if p.value_area_high > 0]
        
        merged_va_low = min(all_va_lows) if all_va_lows else 0
        merged_va_high = max(all_va_highs) if all_va_highs else 0
        
        # Средняя уверенность
        avg_confidence = sum(p.confidence for p in profiles) / len(profiles)
        
        # Общий объем
        total_volume = sum(p.total_volume for p in profiles)
        
        merged = VolumeProfileResult(
            poc_price=weighted_poc,
            poc_volume=sum(p.poc_volume for p in profiles),
            value_area_high=merged_va_high,
            value_area_low=merged_va_low,
            value_area_volume=sum(p.value_area_volume for p in profiles),
            total_volume=total_volume,
            profile_type=self._determine_merged_type(profiles),
            confidence=avg_confidence
        )
        
        logger.info(f"Объединено {len(profiles)} профилей. POC={merged.poc_price:.2f}")
        
        return merged
    
    def _determine_merged_type(self, profiles: List[VolumeProfileResult]) -> str:
        """Определение типа объединенного профиля"""
        if not profiles:
            return "unknown"
        
        types = [p.profile_type for p in profiles]
        bullish_count = types.count("bullish")
        bearish_count = types.count("bearish")
        
        if bullish_count > bearish_count:
            return "bullish"
        elif bearish_count > bullish_count:
            return "bearish"
        else:
            return "balanced"
