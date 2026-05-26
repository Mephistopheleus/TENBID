"""
TENBID v2.0 - Capital Flow Controller
Модуль динамического управления капиталом и рисками.
Контролирует соотношение открытых сделок, баланса и просадки.
Защищает от маржин-колла и оптимизирует использование маржи.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

@dataclass
class PositionLimits:
    """Лимиты для позиций"""
    max_positions: int = 5  # Максимальное количество одновременных позиций
    max_margin_usage: float = 0.8  # Максимальное использование маржи (80%)
    max_drawdown_percent: float = 0.15  # Максимальная просадка (15%)
    min_balance_reserve: float = 10.0  # Минимальный резерв баланса в USDT
    
@dataclass
class CapitalState:
    """Текущее состояние капитала"""
    total_balance: float = 50.0  # Стартовый баланс (Testnet)
    used_margin: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    open_positions_count: int = 0
    current_drawdown: float = 0.0
    peak_balance: float = 50.0
    
    @property
    def available_balance(self) -> float:
        """Свободный баланс"""
        return max(0.0, self.total_balance - self.used_margin)
    
    @property
    def equity(self) -> float:
        """Капитал с учетом нереализованного PnL"""
        return self.total_balance + self.unrealized_pnl
    
    @property
    def drawdown_percent(self) -> float:
        """Процент просадки от пика"""
        if self.peak_balance <= 0:
            return 0.0
        current_equity = self.equity
        if current_equity < self.peak_balance:
            return (self.peak_balance - current_equity) / self.peak_balance
        return 0.0

@dataclass
class RiskAssessment:
    """Оценка рисков для новой сделки"""
    allowed: bool = False
    reason: str = ""
    suggested_size: float = 0.0
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL

class CapitalFlowController:
    """
    Контроллер потока капитала.
    Динамически управляет лимитами позиций на основе:
    - Текущего баланса
    - Уровня просадки
    - Волатильности рынка
    - Уверенности сигналов
    """
    
    def __init__(self, initial_balance: float = 50.0):
        self.state = CapitalState(total_balance=initial_balance, peak_balance=initial_balance)
        self.limits = PositionLimits()
        self.position_sizes: Dict[str, float] = {}  # ID позиции -> размер
        logger.info(f"CapitalFlowController инициализирован с балансом {initial_balance} USDT")
    
    def update_state(self, 
                     used_margin: float, 
                     unrealized_pnl: float, 
                     open_positions_count: int,
                     realized_pnl_change: float = 0.0):
        """Обновление состояния капитала"""
        self.state.used_margin = used_margin
        self.state.unrealized_pnl = unrealized_pnl
        self.state.open_positions_count = open_positions_count
        
        if realized_pnl_change != 0:
            self.state.realized_pnl += realized_pnl_change
            self.state.total_balance += realized_pnl_change
            
            # Обновление пика баланса
            if self.state.total_balance > self.state.peak_balance:
                self.state.peak_balance = self.state.total_balance
        
        self.state.current_drawdown = self.state.drawdown_percent
        
        logger.debug(f"Состояние капитала обновлено: Баланс={self.state.total_balance:.2f}, "
                    f"Использовано маржи={self.state.used_margin:.2f}, "
                    f"Просадка={self.state.current_drawdown:.2%}")
    
    def assess_risk(self, 
                   required_margin: float, 
                   signal_confidence: float = 0.5,
                   market_volatility: float = 0.0) -> RiskAssessment:
        """
        Оценка риска для открытия новой позиции.
        
        Args:
            required_margin: Требуемая маржа для сделки
            signal_confidence: Уверенность сигнала (0.0 - 1.0)
            market_volatility: Волатильность рынка (нормализованная)
            
        Returns:
            RiskAssessment с решением и рекомендациями
        """
        # Проверка 1: Лимит количества позиций
        if self.state.open_positions_count >= self.limits.max_positions:
            return RiskAssessment(
                allowed=False,
                reason=f"Достигнут лимит позиций ({self.limits.max_positions})",
                risk_level="HIGH"
            )
        
        # Проверка 2: Доступная маржа
        available = self.state.available_balance - self.limits.min_balance_reserve
        if required_margin > available:
            return RiskAssessment(
                allowed=False,
                reason=f"Недостаточно свободной маржи. Доступно: {available:.2f}, Требуется: {required_margin:.2f}",
                suggested_size=available,
                risk_level="CRITICAL"
            )
        
        # Проверка 3: Просадка
        current_dd = self.state.drawdown_percent
        if current_dd >= self.limits.max_drawdown_percent:
            return RiskAssessment(
                allowed=False,
                reason=f"Превышен лимит просадки ({current_dd:.2%} >= {self.limits.max_drawdown_percent:.2%})",
                risk_level="CRITICAL"
            )
        
        # Динамическое уменьшение размера позиции при высокой просадке
        size_multiplier = 1.0
        if current_dd > 0.05:  # Если просадка > 5%
            size_multiplier = max(0.2, 1.0 - (current_dd / self.limits.max_drawdown_percent))
        
        # Корректировка по уверенности сигнала
        confidence_factor = signal_confidence
        if signal_confidence < 0.3:
            size_multiplier *= 0.5  # Уменьшаем размер при низкой уверенности
        elif signal_confidence > 0.8:
            size_multiplier = min(1.5, size_multiplier * 1.2)  # Немного увеличиваем при высокой
        
        # Корректировка по волатильности
        if market_volatility > 0.8:
            size_multiplier *= 0.7  # Уменьшаем при высокой волатильности
        
        suggested_size = required_margin * size_multiplier
        
        # Определение уровня риска
        risk_level = "LOW"
        if current_dd > 0.1 or size_multiplier < 0.5:
            risk_level = "HIGH"
        elif current_dd > 0.05 or size_multiplier < 0.8:
            risk_level = "MEDIUM"
        
        return RiskAssessment(
            allowed=True,
            reason="Риск в допустимых пределах",
            suggested_size=suggested_size,
            risk_level=risk_level
        )
    
    def register_position(self, position_id: str, size: float):
        """Регистрация открытой позиции"""
        self.position_sizes[position_id] = size
        logger.info(f"Зарегистрирована позиция {position_id} размером {size}")
    
    def close_position(self, position_id: str, pnl: float):
        """Закрытие позиции и обновление статистики"""
        if position_id in self.position_sizes:
            del self.position_sizes[position_id]
        
        # Обновление реализованного PnL происходит через update_state
        logger.info(f"Позиция {position_id} закрыта с PnL: {pnl}")
    
    def get_dynamic_limits(self) -> Dict:
        """Получение текущих динамических лимитов"""
        current_dd = self.state.drawdown_percent
        
        # Динамическая настройка лимитов
        dynamic_max_positions = self.limits.max_positions
        if current_dd > 0.1:
            dynamic_max_positions = max(1, int(self.limits.max_positions * 0.5))
        elif current_dd > 0.05:
            dynamic_max_positions = max(2, int(self.limits.max_positions * 0.75))
        
        return {
            "max_positions": dynamic_max_positions,
            "max_margin_usage": self.limits.max_margin_usage * (1.0 - current_dd),
            "available_balance": self.state.available_balance,
            "current_drawdown": current_dd,
            "risk_level": "HIGH" if current_dd > 0.1 else "MEDIUM" if current_dd > 0.05 else "LOW"
        }
    
    def reset(self, new_balance: Optional[float] = None):
        """Сброс контроллера (для тестов или рестарта)"""
        balance = new_balance if new_balance else self.state.total_balance
        self.state = CapitalState(total_balance=balance, peak_balance=balance)
        self.position_sizes.clear()
        logger.info(f"CapitalFlowController сброшен. Новый баланс: {balance}")
