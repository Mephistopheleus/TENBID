"""
TENBID v2.0 - Futures Execution Module
Модуль исполнения сделок на фьючерсном рынке.
Работает с решениями Probability Matrix, рассчитывает точку входа,
реализует логику "противохода" и управления позициями.
Каждая сделка независима, закрытие в плюс — приоритет.
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import hashlib
import uuid

logger = logging.getLogger(__name__)

@dataclass
class TradeSignal:
    """Сигнал на открытие сделки"""
    direction: int  # 1 (long), -1 (short)
    entry_price: float
    target_price: float
    stop_loss: float
    size_usd: float
    leverage: int = 1
    confidence: float = 0.0
    reason: str = ""
    matrix_decision_id: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    id: str = ""
    
    def __post_init__(self):
        if not self.id:
            self.id = hashlib.md5(f"{self.timestamp.isoformat()}{self.entry_price}{self.direction}".encode()).hexdigest()[:14]
    
    @property
    def expected_profit_percent(self) -> float:
        """Ожидаемый процент прибыли"""
        if self.direction > 0:
            return (self.target_price - self.entry_price) / self.entry_price * 100
        else:
            return (self.entry_price - self.target_price) / self.entry_price * 100
    
    @property
    def risk_reward_ratio(self) -> float:
        """Соотношение риск/прибыль"""
        if self.direction > 0:
            profit = self.target_price - self.entry_price
            loss = self.entry_price - self.stop_loss
        else:
            profit = self.entry_price - self.target_price
            loss = self.stop_loss - self.entry_price
        
        if loss <= 0:
            return 0.0
        
        return profit / loss
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "direction": "LONG" if self.direction > 0 else "SHORT",
            "entry_price": self.entry_price,
            "target_price": self.target_price,
            "stop_loss": self.stop_loss,
            "size_usd": self.size_usd,
            "leverage": self.leverage,
            "confidence": self.confidence,
            "expected_profit_percent": self.expected_profit_percent,
            "risk_reward_ratio": self.risk_reward_ratio,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat()
        }

@dataclass
class Position:
    """Открытая позиция"""
    symbol: str
    side: str  # "BUY" или "SELL"
    size: float  # В монетах
    entry_price: float
    current_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    leverage: int = 1
    margin: float = 0.0
    open_time: datetime = field(default_factory=datetime.utcnow)
    close_time: Optional[datetime] = None
    status: str = "open"  # open, closing, closed
    signal_id: str = ""
    id: str = ""
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:12]
    
    def update_pnl(self, current_price: float):
        """Обновление нереализованного PnL"""
        self.current_price = current_price
        
        if self.side == "BUY":
            self.unrealized_pnl = (current_price - self.entry_price) * self.size
        else:
            self.unrealized_pnl = (self.entry_price - current_price) * self.size
    
    @property
    def pnl_percent(self) -> float:
        """Процент прибыли/убытка от маржи"""
        if self.margin <= 0:
            return 0.0
        return self.unrealized_pnl / self.margin * 100
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side,
            "size": self.size,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "unrealized_pnl": self.unrealized_pnl,
            "pnl_percent": self.pnl_percent,
            "status": self.status,
            "open_time": self.open_time.isoformat()
        }

class FuturesExecution:
    """
    Модуль исполнения фьючерсных сделок v2.0.
    
    Принципы:
    1. Каждая сделка независима (свой горизонт, свои цели)
    2. Закрытие в плюс перед открытием новой позиции
    3. Противоход при развороте вектора Матрицы
    4. Динамический трейлинг стоп
    5. Интеграция с Capital Flow Controller
    """
    
    def __init__(self, 
                 symbol: str = "BTCUSDT",
                 default_leverage: int = 5,
                 min_profit_threshold: float = 0.5,  # Минимальная прибыль % для закрытия
                 trailing_stop_percent: float = 0.3):  # Трейлинг стоп %
        """
        Инициализация исполнителя.
        
        Args:
            symbol: Торговая пара
            default_leverage: Плечо по умолчанию
            min_profit_threshold: Минимальный профит % для фиксации
            trailing_stop_percent: Процент трейлинг стопа
        """
        self.symbol = symbol
        self.default_leverage = default_leverage
        self.min_profit_threshold = min_profit_threshold
        self.trailing_stop_percent = trailing_stop_percent
        
        self.positions: Dict[str, Position] = {}  # ID -> Position
        self.closed_positions: List[Position] = []
        self.pending_signals: List[TradeSignal] = []
        
        # Статистика
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0.0
        
        logger.info(f"FuturesExecution v2.0 инициализирован: {symbol}, leverage={default_leverage}")
    
    def analyze_matrix_decision(self, 
                               decision: Any,  # MatrixDecision
                               current_price: float,
                               capital_available: float,
                               signal_confidence: float) -> Optional[TradeSignal]:
        """
        Анализ решения Матрицы и генерация торгового сигнала.
        
        Args:
            decision: Решение от ProbabilityMatrix
            current_price: Текущая цена
            capital_available: Доступный капитал
            signal_confidence: Уверенность сигнала
            
        Returns:
            TradeSignal или None
        """
        if decision.overall_confidence < 0.4:
            logger.debug("Низкая уверенность матрицы, пропуск сигнала")
            return None
        
        # Получение лучшей зоны
        best_zone = decision.get_best_zone(decision.overall_direction)
        
        if not best_zone:
            logger.debug("Нет подходящей зоны для входа")
            return None
        
        # Расчет точки входа (на краю зоны)
        if decision.overall_direction > 0:
            entry_price = best_zone.price_low * 1.001  # Чуть выше нижней границы
            target_price = best_zone.price_high * 1.02  # С запасом
            stop_loss = best_zone.price_low * 0.995  # Чуть ниже
        else:
            entry_price = best_zone.price_high * 0.999  # Чуть ниже верхней границы
            target_price = best_zone.price_low * 0.98  # С запасом
            stop_loss = best_zone.price_high * 1.005  # Чуть выше
        
        # Проверка риск/прибыль
        if decision.overall_direction > 0:
            profit_dist = target_price - entry_price
            loss_dist = entry_price - stop_loss
        else:
            profit_dist = entry_price - target_price
            loss_dist = stop_loss - entry_price
        
        if loss_dist <= 0 or profit_dist / loss_dist < 1.5:
            logger.debug("Плохое соотношение риск/прибыль")
            return None
        
        # Расчет размера позиции
        risk_per_trade = capital_available * 0.02  # 2% риска на сделку
        size_usd = risk_per_trade / (loss_dist / entry_price)
        
        # Ограничение по доступному капиталу
        max_size = capital_available * self.default_leverage * 0.5  # Макс 50% маржи
        size_usd = min(size_usd, max_size)
        
        if size_usd < 10:  # Минимальный размер сделки
            logger.debug("Размер сделки слишком мал")
            return None
        
        signal = TradeSignal(
            direction=decision.overall_direction,
            entry_price=entry_price,
            target_price=target_price,
            stop_loss=stop_loss,
            size_usd=size_usd,
            leverage=self.default_leverage,
            confidence=decision.overall_confidence * signal_confidence,
            reason=f"Matrix zone: {best_zone.zone_type}, prob={best_zone.probability:.2f}",
            matrix_decision_id=decision.id
        )
        
        logger.info(f"Сигнал сгенерирован: {signal.direction}, entry={signal.entry_price:.2f}, target={signal.target_price:.2f}")
        
        return signal
    
    def check_countertrade_opportunity(self,
                                      decision: Any,
                                      current_price: float,
                                      existing_position: Position) -> Optional[TradeSignal]:
        """
        Проверка возможности противохода.
        Если Матрица показывает разворот, закрываем старую позицию в плюс
        и открываем новую в противоположном направлении.
        
        Args:
            decision: Решение Матрицы
            current_price: Текущая цена
            existing_position: Существующая позиция
            
        Returns:
            TradeSignal для противохода или None
        """
        if not existing_position or existing_position.status != "open":
            return None
        
        # Расчет вероятности разворота
        reversal_prob = decision.get_reversal_probability(current_price)
        
        if reversal_prob < 0.6:  # Низкая вероятность разворота
            return None
        
        # Проверка, есть ли прибыль для закрытия
        existing_position.update_pnl(current_price)
        
        if existing_position.unrealized_pnl <= 0:
            # Нет прибыли, просто закрываем по стопу или ждем
            logger.debug("Противоход: нет прибыли для фиксации")
            return None
        
        # Определение направления для новой сделки
        new_direction = -1 if existing_position.side == "BUY" else 1
        
        # Получение зоны для нового направления
        best_zone = decision.get_best_zone(new_direction)
        
        if not best_zone:
            return None
        
        # Создание сигнала для противохода
        if new_direction > 0:
            entry_price = best_zone.price_low * 1.001
            target_price = best_zone.price_high * 1.02
            stop_loss = best_zone.price_low * 0.995
        else:
            entry_price = best_zone.price_high * 0.999
            target_price = best_zone.price_low * 0.98
            stop_loss = best_zone.price_high * 1.005
        
        signal = TradeSignal(
            direction=new_direction,
            entry_price=entry_price,
            target_price=target_price,
            stop_loss=stop_loss,
            size_usd=existing_position.margin * self.default_leverage,  # Тот же размер
            leverage=self.default_leverage,
            confidence=reversal_prob,
            reason=f"Countertrade: reversal_prob={reversal_prob:.2f}, closing {existing_position.id} in profit"
        )
        
        logger.info(f"Возможность противохода: direction={new_direction}, confidence={reversal_prob:.2f}")
        
        return signal
    
    def manage_trailing_stop(self, position: Position, current_price: float) -> Optional[float]:
        """
        Управление трейлинг стопом.
        
        Args:
            position: Позиция
            current_price: Текущая цена
            
        Returns:
            Новый уровень стоп-лосса или None
        """
        if position.status != "open":
            return None
        
        position.update_pnl(current_price)
        
        # Если есть прибыль, двигаем стоп
        if position.pnl_percent > self.min_profit_threshold:
            if position.side == "BUY":
                new_stop = current_price * (1 - self.trailing_stop_percent / 100)
                if position.stop_loss is None or new_stop > position.stop_loss:
                    position.stop_loss = new_stop
                    logger.debug(f"Trailing stop updated for {position.id}: {new_stop:.2f}")
                    return new_stop
            else:  # SHORT
                new_stop = current_price * (1 + self.trailing_stop_percent / 100)
                if position.stop_loss is None or new_stop < position.stop_loss:
                    position.stop_loss = new_stop
                    logger.debug(f"Trailing stop updated for {position.id}: {new_stop:.2f}")
                    return new_stop
        
        return None
    
    def should_close_position(self, position: Position, current_price: float) -> Tuple[bool, str]:
        """
        Проверка условий для закрытия позиции.
        
        Args:
            position: Позиция
            current_price: Текущая цена
            
        Returns:
            (should_close, reason)
        """
        if position.status != "open":
            return False, ""
        
        position.update_pnl(current_price)
        
        # Проверка стоп-лосса
        if position.stop_loss:
            if position.side == "BUY" and current_price <= position.stop_loss:
                return True, "Stop loss hit"
            elif position.side == "SELL" and current_price >= position.stop_loss:
                return True, "Stop loss hit"
        
        # Проверка тейк-профита
        if position.take_profit:
            if position.side == "BUY" and current_price >= position.take_profit:
                return True, "Take profit hit"
            elif position.side == "SELL" and current_price <= position.take_profit:
                return True, "Take profit hit"
        
        # Проверка минимальной прибыли
        if position.pnl_percent >= self.min_profit_threshold:
            return True, f"Profit target reached: {position.pnl_percent:.2f}%"
        
        # Проверка большого убытка (аварийное закрытие)
        if position.pnl_percent <= -5.0:
            return True, "Emergency stop: large loss"
        
        return False, ""
    
    def execute_signal(self, signal: TradeSignal, capital_controller: Any) -> Optional[Position]:
        """
        Исполнение торгового сигнала.
        
        Args:
            signal: Торговый сигнал
            capital_controller: CapitalFlowController для проверки лимитов
            
        Returns:
            Position или None
        """
        # Проверка через контроллер капитала
        required_margin = signal.size_usd / signal.leverage
        
        risk_assessment = capital_controller.assess_risk(
            required_margin=required_margin,
            signal_confidence=signal.confidence
        )
        
        if not risk_assessment.allowed:
            logger.warning(f"Сигнал отклонен контроллером капитала: {risk_assessment.reason}")
            return None
        
        # Корректировка размера если нужно
        actual_size_usd = risk_assessment.suggested_size * signal.leverage
        
        # Расчет размера в монетах
        size_coins = actual_size_usd / signal.entry_price
        
        # Создание позиции
        position = Position(
            symbol=self.symbol,
            side="BUY" if signal.direction > 0 else "SELL",
            size=size_coins,
            entry_price=signal.entry_price,
            current_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.target_price,
            leverage=signal.leverage,
            margin=actual_size_usd / signal.leverage,
            signal_id=signal.id
        )
        
        self.positions[position.id] = position
        self.total_trades += 1
        
        # Регистрация в контроллере капитала
        capital_controller.register_position(position.id, position.margin)
        
        logger.info(f"Позиция открыта: {position.id}, {position.side}, size={position.size:.6f}, entry={position.entry_price:.2f}")
        
        return position
    
    def close_position(self, position_id: str, current_price: float, reason: str = "") -> float:
        """
        Закрытие позиции.
        
        Args:
            position_id: ID позиции
            current_price: Цена закрытия
            reason: Причина закрытия
            
        Returns:
            Реализованный PnL
        """
        if position_id not in self.positions:
            logger.error(f"Позиция {position_id} не найдена")
            return 0.0
        
        position = self.positions[position_id]
        position.update_pnl(current_price)
        
        realized_pnl = position.unrealized_pnl
        
        # Обновление статистики
        position.realized_pnl = realized_pnl
        position.close_time = datetime.utcnow()
        position.status = "closed"
        
        self.total_pnl += realized_pnl
        
        if realized_pnl > 0:
            self.winning_trades += 1
        
        # Перемещение в закрытые
        self.closed_positions.append(position)
        del self.positions[position_id]
        
        logger.info(f"Позиция {position_id} закрыта: PnL={realized_pnl:.2f}, reason={reason}")
        
        return realized_pnl
    
    def get_active_positions_summary(self) -> Dict:
        """Получение сводки по активным позициям"""
        if not self.positions:
            return {"count": 0, "total_unrealized_pnl": 0.0}
        
        total_unrealized = sum(p.unrealized_pnl for p in self.positions.values())
        
        return {
            "count": len(self.positions),
            "total_unrealized_pnl": total_unrealized,
            "positions": [p.to_dict() for p in self.positions.values()]
        }
    
    def get_statistics(self) -> Dict:
        """Получение статистики исполнения"""
        win_rate = self.winning_trades / self.total_trades * 100 if self.total_trades > 0 else 0
        
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "win_rate": win_rate,
            "total_pnl": self.total_pnl,
            "active_positions": len(self.positions),
            "closed_positions": len(self.closed_positions)
        }
