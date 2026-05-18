"""
Контекстный профиль данных.
Позволяет маркировать сигналы от модулей в зависимости от условий рынка.
Автотюнер будет оценивать полезность сигнала в конкретном контексте.
"""
import hashlib
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class MarketRegime(Enum):
    TREND_STRONG = "trend_strong"
    TREND_WEAK = "trend_weak"
    FLAT_NARROW = "flat_narrow"
    FLAT_WIDE = "flat_wide"
    VOLATILE = "volatile"
    CALM = "calm"

@dataclass
class ContextProfile:
    """
    Уникальный идентификатор контекста для сигнала.
    Пример: {regime: 'trend_strong', volatility: 'high', volume: 'above_avg'}
    """
    regime: MarketRegime
    volatility_level: str  # 'low', 'medium', 'high'
    volume_profile: str    # 'below_avg', 'avg', 'above_avg'
    trend_direction: str   # 'up', 'down', 'none'
    timeframe_cluster: str # 'short', 'medium', 'long'
    
    def get_id(self) -> str:
        """Генерирует уникальный ID профиля."""
        profile_str = f"{self.regime.value}_{self.volatility_level}_{self.volume_profile}_{self.trend_direction}_{self.timeframe_cluster}"
        return hashlib.md5(profile_str.encode()).hexdigest()[:8]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'regime': self.regime.value,
            'volatility': self.volatility_level,
            'volume': self.volume_profile,
            'trend': self.trend_direction,
            'timeframe': self.timeframe_cluster,
            'profile_id': self.get_id()
        }

class ContextProfiler:
    """Управляет созданием и кэшированием контекстных профилей."""
    
    def __init__(self):
        self.cache: Dict[str, ContextProfile] = {}
        
    def create_profile(self, regime: MarketRegime, volatility: float, 
                      volume_ratio: float, trend_dir: str, tf_cluster: str) -> ContextProfile:
        """Создает контекстный профиль на основе текущих рыночных данных."""
        
        # Классификация волатильности
        if volatility < 0.001:
            vol_level = 'low'
        elif volatility < 0.005:
            vol_level = 'medium'
        else:
            vol_level = 'high'
            
        # Классификация объема
        if volume_ratio < 0.8:
            vol_profile = 'below_avg'
        elif volume_ratio > 1.2:
            vol_profile = 'above_avg'
        else:
            vol_profile = 'avg'
            
        profile = ContextProfile(
            regime=regime,
            volatility_level=vol_level,
            volume_profile=vol_profile,
            trend_direction=trend_dir,
            timeframe_cluster=tf_cluster
        )
        
        profile_id = profile.get_id()
        self.cache[profile_id] = profile
        
        logger.debug(f"ContextProfile created: {profile_id} -> {profile.to_dict()}")
        return profile
    
    def get_profile(self, profile_id: str) -> Optional[ContextProfile]:
        """Получает профиль по ID."""
        return self.cache.get(profile_id)
    
    def clear_old(self, max_cache_size: int = 100):
        """Очистка старого кэша при переполнении."""
        if len(self.cache) > max_cache_size:
            # Оставляем только последние 50
            items = list(self.cache.items())
            self.cache = dict(items[-50:])
            logger.debug(f"ContextProfiler cache cleaned, size={len(self.cache)}")
