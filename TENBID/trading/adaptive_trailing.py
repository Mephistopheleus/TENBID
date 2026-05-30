"""
Adaptive Trailing - адаптивный трейлинг стоп на основе матрицы прогнозов.

Логика:
1. Как можно быстрее переместить SL в безубыток
2. Подтягивать SL с учётом:
   - ATR (не выбить раньше времени)
   - Прогноза матрицы (куда движется цена)
   - Параметров автотюнера (агрессивность)
3. Баланс: не слишком близко, не слишком далеко

Все параметры настраиваются автотюнером.
"""

import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from core.probability_matrix import ProbabilityMatrix, MarketScenario

logger = logging.getLogger(__name__)


class AdaptiveTrailing:
    """
    Адаптивный трейлинг стоп на основе матрицы прогнозов.
    Все параметры от автотюнера - никаких хардкодов.
    """
    
    def __init__(self, config, autotuner):
        """
        Инициализация адаптивного трейлинга.
        
        Args:
            config: Конфигурация системы
            autotuner: Экземпляр Autotuner для получения параметров
        """
        self.config = config
        self.autotuner = autotuner
        
        # Параметры от автотюнера (с дефолтными значениями)
        self.params = self._get_params_from_autotuner()
        
        logger.info(f"AdaptiveTrailing initialized with params: {self.params}")
    
    def _get_params_from_autotuner(self) -> Dict[str, Any]:
        """
        Получает параметры от автотюнера.
        В будущем autotuner будет возвращать оптимизированные параметры.
        """
        # TODO: Реализовать метод get_trailing_params() в autotuner
        # Пока используем дефолтные значения
        return {
            # Безубыток
            'breakeven_trigger_pct': 0.5,          # При какой прибыли переходить в безубыток
            'breakeven_offset_pct': 0.1,           # Смещение от точки входа (для комиссий)
            
            # Базовый трейлинг
            'base_trail_distance_atr': 1.5,        # Базовое расстояние = ATR * множитель
            'min_trail_distance_pct': 0.3,         # Минимальное расстояние (%)
            'max_trail_distance_pct': 3.0,         # Максимальное расстояние (%)
            
            # Агрессивность
            'aggressive_trail_multiplier': 0.7,    # Множитель для агрессивного трейлинга
            'conservative_trail_multiplier': 1.3,  # Множитель для консервативного трейлинга
            
            # Прогноз матрицы
            'forecast_horizon_minutes': 15,        # Горизонт прогноза для анализа
            'negative_forecast_threshold': 0.6,    # Порог негативного прогноза
            'positive_forecast_threshold': 0.7,    # Порог позитивного прогноза
            
            # Динамическая корректировка
            'profit_acceleration_threshold': 2.0,  # При прибыли > X% ускорить трейлинг
            'profit_acceleration_multiplier': 0.8, # Множитель при ускорении
            
            # Защита от волатильности
            'volatility_multiplier_high': 1.5,     # Множитель при высокой волатильности
            'volatility_threshold_atr_ratio': 1.5, # Порог высокой волатильности (ATR/средний ATR)
            
            # Негативные сценарии (когда подтягивать агрессивнее)
            'negative_scenarios': [
                'trend_down', 'trend_continuation_down', 'breakout_down',
                'support_breakdown', 'reversal_down', 'pattern_reversal_down',
                'fractal_bearish_reversal', 'pattern_rejection',
                'pattern_continuation_down', 'chart_breakdown', 'chart_double_top',
                'resistance_bounce'  # Для лонгов - отскок от сопротивления негативен
            ]
        }
    
    def update_trailing(self, trade: Dict[str, Any], matrix: ProbabilityMatrix,
                       current_price: float, atr: float,
                       market_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Обновляет уровень трейлинг стопа для активной сделки.
        
        Args:
            trade: Информация об активной сделке
                {
                    'entry_price': float,
                    'current_sl': float,
                    'side': 'BUY' | 'SELL',
                    'high_since_entry': float,
                    'low_since_entry': float,
                    'entry_time': datetime
                }
            matrix: Матрица прогнозов
            current_price: Текущая цена
            atr: Текущий ATR
            market_context: Дополнительный контекст рынка
        
        Returns:
            {
                'new_sl': float,
                'action': 'MOVE_TO_BREAKEVEN' | 'TRAIL_AGGRESSIVE' | 'TRAIL_CONSERVATIVE' | 'HOLD',
                'distance_from_price_pct': float,
                'reasoning': str,
                'should_update': bool
            }
        """
        entry_price = trade['entry_price']
        current_sl = trade['current_sl']
        side = trade['side']
        high_since_entry = trade.get('high_since_entry', current_price)
        
        # Рассчитываем текущую прибыль
        if side == 'BUY':
            profit_pct = (current_price - entry_price) / entry_price * 100
            is_in_profit = current_price > entry_price
        else:  # SELL
            profit_pct = (entry_price - current_price) / entry_price * 100
            is_in_profit = current_price < entry_price
        
        # ПРИОРИТЕТ 1: Переход в безубыток
        if is_in_profit and profit_pct >= self.params['breakeven_trigger_pct']:
            breakeven_result = self._check_breakeven(
                entry_price, current_sl, side, profit_pct
            )
            if breakeven_result['should_move']:
                return breakeven_result
        
        # ПРИОРИТЕТ 2: Адаптивное подтягивание на основе прогноза
        if is_in_profit:
            # Анализируем прогноз матрицы
            forecast_analysis = self._analyze_forecast(
                matrix, current_price, side, self.params['forecast_horizon_minutes']
            )
            
            # Определяем стратегию трейлинга
            if forecast_analysis['is_negative']:
                # Прогноз ухудшился - агрессивный трейлинг
                return self._aggressive_trail(
                    entry_price, current_price, current_sl, side, atr,
                    high_since_entry, profit_pct, forecast_analysis
                )
            else:
                # Прогноз хороший - консервативный трейлинг
                return self._conservative_trail(
                    entry_price, current_price, current_sl, side, atr,
                    high_since_entry, profit_pct, forecast_analysis
                )
        
        # Не в прибыли - не трогаем SL
        return {
            'new_sl': current_sl,
            'action': 'HOLD',
            'distance_from_price_pct': abs(current_price - current_sl) / current_price * 100,
            'reasoning': f"Not in profit yet (P&L: {profit_pct:.2f}%)",
            'should_update': False
        }
    
    def _check_breakeven(self, entry_price: float, current_sl: float,
                        side: str, profit_pct: float) -> Dict[str, Any]:
        """
        Проверяет, нужно ли переместить SL в безубыток.
        """
        # Рассчитываем точку безубытка с учётом комиссий
        breakeven_offset = self.params['breakeven_offset_pct'] / 100
        
        if side == 'BUY':
            breakeven_price = entry_price * (1 + breakeven_offset)
            should_move = current_sl < breakeven_price
        else:  # SELL
            breakeven_price = entry_price * (1 - breakeven_offset)
            should_move = current_sl > breakeven_price
        
        if should_move:
            distance_pct = abs(breakeven_price - entry_price) / entry_price * 100
            return {
                'new_sl': breakeven_price,
                'action': 'MOVE_TO_BREAKEVEN',
                'distance_from_price_pct': distance_pct,
                'reasoning': f"Moving to breakeven at {profit_pct:.2f}% profit (offset: {self.params['breakeven_offset_pct']}%)",
                'should_update': True,
                'should_move': True
            }
        
        return {'should_move': False}
    
    def _analyze_forecast(self, matrix: ProbabilityMatrix, current_price: float,
                         side: str, horizon_minutes: int) -> Dict[str, Any]:
        """
        Анализирует прогноз матрицы для определения стратегии трейлинга.
        
        Returns:
            {
                'is_negative': bool,
                'is_positive': bool,
                'max_probability': float,
                'dominant_scenario': str,
                'reasoning': str
            }
        """
        # Получаем зоны вероятности в заданном горизонте
        zones = matrix.find_max_probability_zones()
        
        if not zones:
            return {
                'is_negative': False,
                'is_positive': False,
                'max_probability': 0.0,
                'dominant_scenario': 'unknown',
                'reasoning': 'No forecast zones available'
            }
        
        # Фильтруем зоны по временному горизонту
        relevant_zones = [z for z in zones if z.time_minutes <= horizon_minutes]
        
        if not relevant_zones:
            return {
                'is_negative': False,
                'is_positive': False,
                'max_probability': 0.0,
                'dominant_scenario': 'unknown',
                'reasoning': f'No zones within {horizon_minutes}m horizon'
            }
        
        # Берём зону с максимальной вероятностью
        top_zone = relevant_zones[0]
        scenario = top_zone.scenario.value
        probability = top_zone.probability
        
        # Определяем, негативный ли прогноз для текущей позиции
        is_negative = False
        is_positive = False
        
        if side == 'BUY':
            # Для лонга негативны медвежьи сценарии
            if scenario in self.params['negative_scenarios']:
                is_negative = probability >= self.params['negative_forecast_threshold']
            else:
                is_positive = probability >= self.params['positive_forecast_threshold']
        else:  # SELL
            # Для шорта негативны бычьи сценарии
            bullish_scenarios = [
                'trend_up', 'trend_continuation_up', 'breakout_up',
                'resistance_breakout', 'support_bounce', 'reversal_up',
                'pattern_reversal_up', 'fractal_bullish_reversal',
                'pattern_bounce', 'pattern_continuation_up',
                'chart_breakout_up', 'chart_double_bottom'
            ]
            if scenario in bullish_scenarios:
                is_negative = probability >= self.params['negative_forecast_threshold']
            else:
                is_positive = probability >= self.params['positive_forecast_threshold']
        
        reasoning = f"Forecast: {scenario} @ {top_zone.time_minutes}m, prob={probability:.2f}"
        
        return {
            'is_negative': is_negative,
            'is_positive': is_positive,
            'max_probability': probability,
            'dominant_scenario': scenario,
            'reasoning': reasoning
        }
    
    def _aggressive_trail(self, entry_price: float, current_price: float,
                         current_sl: float, side: str, atr: float,
                         high_since_entry: float, profit_pct: float,
                         forecast: Dict[str, Any]) -> Dict[str, Any]:
        """
        Агрессивный трейлинг - подтягиваем SL ближе к цене.
        Используется когда прогноз ухудшился.
        """
        # Базовое расстояние с агрессивным множителем
        base_distance = atr * self.params['base_trail_distance_atr']
        aggressive_distance = base_distance * self.params['aggressive_trail_multiplier']
        
        # Дополнительное ускорение при большой прибыли
        if profit_pct >= self.params['profit_acceleration_threshold']:
            aggressive_distance *= self.params['profit_acceleration_multiplier']
        
        # Рассчитываем новый SL
        if side == 'BUY':
            # Для лонга: SL под текущей ценой
            new_sl = current_price - aggressive_distance
            # Не опускаем SL
            new_sl = max(new_sl, current_sl)
        else:  # SELL
            # Для шорта: SL над текущей ценой
            new_sl = current_price + aggressive_distance
            # Не поднимаем SL
            new_sl = min(new_sl, current_sl)
        
        # Применяем ограничения
        distance_pct = abs(new_sl - current_price) / current_price * 100
        distance_pct = max(
            self.params['min_trail_distance_pct'],
            min(distance_pct, self.params['max_trail_distance_pct'])
        )
        
        # Пересчитываем SL с учётом ограничений
        if side == 'BUY':
            new_sl = current_price * (1 - distance_pct / 100)
            new_sl = max(new_sl, current_sl)  # Не опускаем
        else:
            new_sl = current_price * (1 + distance_pct / 100)
            new_sl = min(new_sl, current_sl)  # Не поднимаем
        
        should_update = new_sl != current_sl
        
        reasoning = (f"Aggressive trail: {forecast['reasoning']}, "
                    f"profit={profit_pct:.2f}%, distance={distance_pct:.2f}%")
        
        return {
            'new_sl': new_sl,
            'action': 'TRAIL_AGGRESSIVE',
            'distance_from_price_pct': distance_pct,
            'reasoning': reasoning,
            'should_update': should_update
        }
    
    def _conservative_trail(self, entry_price: float, current_price: float,
                           current_sl: float, side: str, atr: float,
                           high_since_entry: float, profit_pct: float,
                           forecast: Dict[str, Any]) -> Dict[str, Any]:
        """
        Консервативный трейлинг - даём цене больше пространства.
        Используется когда прогноз хороший.
        """
        # Базовое расстояние с консервативным множителем
        base_distance = atr * self.params['base_trail_distance_atr']
        conservative_distance = base_distance * self.params['conservative_trail_multiplier']
        
        # Рассчитываем новый SL от максимума прибыли
        if side == 'BUY':
            # Для лонга: SL под максимумом с консервативным отступом
            new_sl = high_since_entry - conservative_distance
            # Не опускаем SL
            new_sl = max(new_sl, current_sl)
        else:  # SELL
            # Для шорта: SL над минимумом с консервативным отступом
            low_since_entry = current_price  # Упрощение, можно передавать отдельно
            new_sl = low_since_entry + conservative_distance
            # Не поднимаем SL
            new_sl = min(new_sl, current_sl)
        
        # Применяем ограничения
        distance_pct = abs(new_sl - current_price) / current_price * 100
        distance_pct = max(
            self.params['min_trail_distance_pct'],
            min(distance_pct, self.params['max_trail_distance_pct'])
        )
        
        # Пересчитываем SL с учётом ограничений
        if side == 'BUY':
            new_sl = current_price * (1 - distance_pct / 100)
            new_sl = max(new_sl, current_sl)  # Не опускаем
        else:
            new_sl = current_price * (1 + distance_pct / 100)
            new_sl = min(new_sl, current_sl)  # Не поднимаем
        
        should_update = new_sl != current_sl
        
        reasoning = (f"Conservative trail: {forecast['reasoning']}, "
                    f"profit={profit_pct:.2f}%, distance={distance_pct:.2f}%")
        
        return {
            'new_sl': new_sl,
            'action': 'TRAIL_CONSERVATIVE',
            'distance_from_price_pct': distance_pct,
            'reasoning': reasoning,
            'should_update': should_update
        }
    
    def calculate_initial_sl(self, entry_price: float, side: str, atr: float,
                            market_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Рассчитывает начальный Stop Loss при открытии позиции.
        
        Args:
            entry_price: Цена входа
            side: Направление ('BUY' или 'SELL')
            atr: Текущий ATR
            market_context: Дополнительный контекст
        
        Returns:
            {
                'sl_price': float,
                'sl_distance_pct': float,
                'reasoning': str
            }
        """
        # Базовое расстояние
        base_distance = atr * self.params['base_trail_distance_atr']
        
        # Корректировка на волатильность
        if market_context and 'volatility_ratio' in market_context:
            vol_ratio = market_context['volatility_ratio']
            if vol_ratio > self.params['volatility_threshold_atr_ratio']:
                base_distance *= self.params['volatility_multiplier_high']
        
        # Рассчитываем SL
        if side == 'BUY':
            sl_price = entry_price - base_distance
        else:  # SELL
            sl_price = entry_price + base_distance
        
        sl_distance_pct = abs(sl_price - entry_price) / entry_price * 100
        
        # Применяем ограничения
        sl_distance_pct = max(
            self.params['min_trail_distance_pct'],
            min(sl_distance_pct, self.params['max_trail_distance_pct'])
        )
        
        # Пересчитываем с учётом ограничений
        if side == 'BUY':
            sl_price = entry_price * (1 - sl_distance_pct / 100)
        else:
            sl_price = entry_price * (1 + sl_distance_pct / 100)
        
        reasoning = f"Initial SL: ATR={atr:.6f}, distance={sl_distance_pct:.2f}%"
        
        return {
            'sl_price': sl_price,
            'sl_distance_pct': sl_distance_pct,
            'reasoning': reasoning
        }
