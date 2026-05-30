"""
Trade Calculator - полный просчёт сделки на основе матрицы прогнозов.

Функционал:
1. Анализ матрицы - поиск оптимальных зон входа
2. Расчёт точки входа (может быть лимитный ордер)
3. Расчёт SL на основе прогноза матрицы
4. Расчёт затрат (комиссии, спред, проскальзывание)
5. Расчёт ожидаемой чистой прибыли
6. Принятие решения: OPEN/HOLD

Все параметры настраиваются автотюнером.
"""

import logging
from typing import Dict, Any, Optional, Tuple, List
from core.probability_matrix import ProbabilityMatrix, ProbabilityZone, MarketScenario

logger = logging.getLogger(__name__)


class TradeCalculator:
    """
    Полный просчёт сделки на основе матрицы прогнозов.
    Все параметры от автотюнера - никаких хардкодов.
    """
    
    def __init__(self, config, autotuner):
        """
        Инициализация калькулятора.
        
        Args:
            config: Конфигурация системы
            autotuner: Экземпляр Autotuner для получения параметров
        """
        self.config = config
        self.autotuner = autotuner
        
        # Параметры от автотюнера (с дефолтными значениями)
        self.params = self._get_params_from_autotuner()
        
        logger.info(f"TradeCalculator initialized with params: {self.params}")
    
    def _get_params_from_autotuner(self) -> Dict[str, Any]:
        """
        Получает параметры от автотюнера.
        В будущем autotuner будет возвращать оптимизированные параметры.
        """
        defaults = {
            'min_probability_threshold': 0.6,      # Минимальная вероятность для входа
            'min_net_profit_pct': 0.5,             # Минимальная чистая прибыль (%)
            'max_sl_distance_pct': 2.0,            # Максимальное расстояние до SL (%)
            'min_sl_distance_pct': 0.3,            # Минимальное расстояние до SL (%)
            'commission_rate': 0.04,               # Комиссия (0.04% = maker/taker)
            'slippage_estimate': 0.05,             # Оценка проскальзывания (%)
            'spread_estimate': 0.02,               # Оценка спреда (%)
            'risk_reward_min': 1.5,                # Минимальное соотношение R/R
            'entry_offset_pct': 0.0,               # Смещение входа от текущей цены (%)
            'use_limit_orders': False,             # Использовать лимитные ордера
            'zone_time_horizon_max': 30,           # Максимальный горизонт зоны (минуты)
            'bullish_scenarios': [                 # Бычьи сценарии
                'trend_up', 'trend_continuation_up', 'breakout_up',
                'resistance_breakout', 'support_bounce', 'reversal_up',
                'pattern_reversal_up', 'fractal_bullish_reversal',
                'pattern_bounce', 'pattern_continuation_up',
                'chart_breakout_up', 'chart_double_bottom'
            ],
            'bearish_scenarios': [                 # Медвежьи сценарии
                'trend_down', 'trend_continuation_down', 'breakout_down',
                'support_breakdown', 'resistance_bounce', 'reversal_down',
                'pattern_reversal_down', 'fractal_bearish_reversal',
                'pattern_rejection', 'pattern_continuation_down',
                'chart_breakdown', 'chart_double_top'
            ]
        }
        if hasattr(self.autotuner, 'get_trade_calculator_params'):
            defaults.update(self.autotuner.get_trade_calculator_params())
        return defaults
    
    def calculate_trade(self, matrix: ProbabilityMatrix, current_price: float, 
                       market_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Полный просчёт сделки на основе матрицы прогнозов.
        
        Args:
            matrix: Матрица вероятностей
            current_price: Текущая цена актива
            market_context: Контекст рынка (ATR, режим, и т.д.)
        
        Returns:
            Словарь с решением и деталями расчёта
        """
        # 1. Получаем зоны максимальной вероятности
        zones = matrix.find_max_probability_zones(
            min_probability=self.params['min_probability_threshold']
        )
        
        if not zones:
            return self._hold_decision("No probability zones found above threshold")
        
        # 2. Анализируем зоны и выбираем лучшую
        best_zone = self._select_best_zone(zones, current_price, market_context)
        
        if not best_zone:
            return self._hold_decision("No suitable zones for entry")
        
        # 3. Определяем направление сделки
        trade_direction = self._determine_trade_direction(best_zone)
        
        if trade_direction == 'NEUTRAL':
            return self._hold_decision(f"Zone scenario {best_zone.scenario.value} is neutral")
        
        # 4. Рассчитываем точку входа
        entry_price = self._calculate_entry_price(
            current_price, best_zone, trade_direction
        )
        
        # 5. Рассчитываем Stop Loss
        sl_price, sl_reasoning = self._calculate_stop_loss(
            entry_price, best_zone, trade_direction, current_price, market_context
        )
        
        # 6. Рассчитываем ожидаемую прибыль
        expected_profit_pct = self._calculate_expected_profit(
            entry_price, best_zone, trade_direction
        )
        
        # 7. Рассчитываем затраты
        costs = self._calculate_costs(entry_price, sl_price, expected_profit_pct)
        
        # 8. Рассчитываем чистую прибыль
        net_profit_pct = expected_profit_pct - costs['total']
        
        # 9. Рассчитываем Risk/Reward
        sl_distance_pct = abs(entry_price - sl_price) / entry_price * 100
        risk_reward = expected_profit_pct / sl_distance_pct if sl_distance_pct > 0 else 0
        
        # 10. Принимаем решение
        decision, reasoning = self._make_decision(
            net_profit_pct, risk_reward, sl_distance_pct, best_zone
        )
        
        # Формируем результат
        result = {
            'decision': decision,
            'trade_direction': trade_direction,
            'entry_price': round(entry_price, 8),
            'sl_price': round(sl_price, 8),
            'sl_distance_pct': round(sl_distance_pct, 3),
            'expected_profit_pct': round(expected_profit_pct, 3),
            'net_profit_pct': round(net_profit_pct, 3),
            'risk_reward': round(risk_reward, 2),
            'costs': {
                'commission': round(costs['commission'], 3),
                'spread': round(costs['spread'], 3),
                'slippage': round(costs['slippage'], 3),
                'total': round(costs['total'], 3)
            },
            'horizon_minutes': int(best_zone.time_minutes),
            'confidence': round(best_zone.probability, 3),
            'scenario': best_zone.scenario.value,
            'zone_price_range': {
                'min': round(best_zone.price_range[0], 8),
                'max': round(best_zone.price_range[1], 8),
                'center': round(best_zone.price_center, 8)
            },
            'reasoning': reasoning,
            'sl_reasoning': sl_reasoning
        }
        
        # Логируем решение
        if decision == 'OPEN':
            logger.info(f"✅ TRADE CALCULATED: {trade_direction} @ {entry_price:.6f}")
            logger.info(f"   SL: {sl_price:.6f} ({sl_distance_pct:.2f}%), "
                       f"Expected: {expected_profit_pct:.2f}%, Net: {net_profit_pct:.2f}%")
            logger.info(f"   R/R: {risk_reward:.2f}, Confidence: {best_zone.probability:.2f}, "
                       f"Scenario: {best_zone.scenario.value}")
            logger.info(f"   Reasoning: {reasoning}")
        else:
            logger.debug(f"❌ HOLD: {reasoning}")
        
        return result
    
    def _select_best_zone(self, zones: List[ProbabilityZone], 
                         current_price: float, 
                         market_context: Dict[str, Any]) -> Optional[ProbabilityZone]:
        """
        Выбирает лучшую зону для входа из списка.
        
        Критерии:
        1. Временной горизонт (не слишком далеко)
        2. Вероятность (выше - лучше)
        3. Расстояние от текущей цены (ближе - лучше)
        4. Соответствие текущему режиму рынка
        """
        suitable_zones = []
        
        for zone in zones:
            # Фильтр 1: Временной горизонт
            if zone.time_minutes > self.params['zone_time_horizon_max']:
                continue
            
            # Фильтр 2: Расстояние от текущей цены (не более 5%)
            price_distance_pct = abs(zone.price_center - current_price) / current_price * 100
            if price_distance_pct > 5.0:
                continue
            
            # Фильтр 3: Только бычьи или медвежьи сценарии (не нейтральные)
            if zone.scenario.value in ['flat', 'consolidation']:
                continue
            
            # Добавляем зону с оценкой
            score = self._score_zone(zone, current_price, market_context)
            suitable_zones.append((zone, score))
        
        if not suitable_zones:
            return None
        
        # Сортируем по оценке и возвращаем лучшую
        suitable_zones.sort(key=lambda x: x[1], reverse=True)
        return suitable_zones[0][0]
    
    def _score_zone(self, zone: ProbabilityZone, current_price: float, 
                   market_context: Dict[str, Any]) -> float:
        """
        Оценивает зону по нескольким критериям.
        Возвращает оценку от 0 до 1.
        """
        score = 0.0
        
        # Критерий 1: Вероятность (вес 40%)
        score += zone.probability * 0.4
        
        # Критерий 2: Близость по времени (вес 20%)
        time_score = 1.0 - (zone.time_minutes / self.params['zone_time_horizon_max'])
        score += time_score * 0.2
        
        # Критерий 3: Близость по цене (вес 20%)
        price_distance_pct = abs(zone.price_center - current_price) / current_price * 100
        price_score = 1.0 - min(price_distance_pct / 5.0, 1.0)
        score += price_score * 0.2
        
        # Критерий 4: Соответствие режиму рынка (вес 20%)
        regime = market_context.get('regime', 'UNKNOWN')
        regime_score = self._match_zone_to_regime(zone, regime)
        score += regime_score * 0.2
        
        return score
    
    def _match_zone_to_regime(self, zone: ProbabilityZone, regime: str) -> float:
        """
        Проверяет соответствие зоны текущему режиму рынка.
        """
        scenario = zone.scenario.value
        
        if regime == 'TRENDING':
            # В тренде предпочитаем продолжение тренда
            if 'continuation' in scenario or 'trend' in scenario:
                return 1.0
            elif 'reversal' in scenario:
                return 0.3
            else:
                return 0.6
        
        elif regime == 'RANGING':
            # В диапазоне предпочитаем отскоки от границ
            if 'bounce' in scenario or 'support' in scenario or 'resistance' in scenario:
                return 1.0
            elif 'breakout' in scenario:
                return 0.4
            else:
                return 0.6
        
        elif regime == 'VOLATILE':
            # В волатильности предпочитаем пробои
            if 'breakout' in scenario or 'breakdown' in scenario:
                return 1.0
            else:
                return 0.5
        
        else:
            # Неизвестный режим - нейтральная оценка
            return 0.5
    
    def _determine_trade_direction(self, zone: ProbabilityZone) -> str:
        """
        Определяет направление сделки на основе сценария зоны.
        
        Returns:
            'LONG', 'SHORT', или 'NEUTRAL'
        """
        scenario = zone.scenario.value
        
        if scenario in self.params['bullish_scenarios']:
            return 'LONG'
        elif scenario in self.params['bearish_scenarios']:
            return 'SHORT'
        else:
            return 'NEUTRAL'
    
    def _calculate_entry_price(self, current_price: float, 
                               zone: ProbabilityZone, 
                               direction: str) -> float:
        """
        Рассчитывает точку входа.
        
        Может быть:
        - Текущая цена (market order)
        - Смещённая цена (limit order)
        """
        if self.params['use_limit_orders']:
            # Лимитный ордер со смещением
            offset_pct = self.params['entry_offset_pct']
            if direction == 'LONG':
                # Для лонга - чуть ниже текущей цены
                return current_price * (1 - offset_pct / 100)
            else:
                # Для шорта - чуть выше текущей цены
                return current_price * (1 + offset_pct / 100)
        else:
            # Рыночный ордер по текущей цене
            return current_price
    
    def _calculate_stop_loss(self, entry_price: float, 
                            zone: ProbabilityZone, 
                            direction: str,
                            current_price: float,
                            market_context: Dict[str, Any]) -> Tuple[float, str]:
        """
        Рассчитывает Stop Loss на основе прогноза матрицы и ATR.
        
        Логика:
        1. Базовое расстояние = ATR * множитель
        2. Корректировка на основе зоны вероятности
        3. Ограничение min/max расстоянием
        
        Returns:
            (sl_price, reasoning)
        """
        atr = market_context.get('atr', current_price * 0.01)
        
        # Базовое расстояние SL = 1.5 * ATR
        base_sl_distance = atr * 1.5
        
        # Корректировка на основе уверенности зоны
        # Высокая уверенность -> можно поставить SL ближе
        # Низкая уверенность -> SL дальше для безопасности
        confidence_multiplier = 1.0 - (zone.probability - 0.5) * 0.5
        confidence_multiplier = max(0.7, min(confidence_multiplier, 1.3))
        
        sl_distance = base_sl_distance * confidence_multiplier
        
        # Применяем ограничения
        sl_distance_pct = sl_distance / entry_price * 100
        sl_distance_pct = max(
            self.params['min_sl_distance_pct'],
            min(sl_distance_pct, self.params['max_sl_distance_pct'])
        )
        
        # Рассчитываем цену SL
        if direction == 'LONG':
            sl_price = entry_price * (1 - sl_distance_pct / 100)
        else:
            sl_price = entry_price * (1 + sl_distance_pct / 100)
        
        reasoning = (f"SL based on ATR={atr:.6f}, confidence={zone.probability:.2f}, "
                    f"distance={sl_distance_pct:.2f}%")
        
        return sl_price, reasoning
    
    def _calculate_expected_profit(self, entry_price: float, 
                                   zone: ProbabilityZone, 
                                   direction: str) -> float:
        """
        Рассчитывает ожидаемую прибыль на основе целевой цены зоны.
        """
        target_price = zone.price_center
        
        if direction == 'LONG':
            profit_pct = (target_price - entry_price) / entry_price * 100
        else:
            profit_pct = (entry_price - target_price) / entry_price * 100
        
        # Ограничиваем разумными пределами (0.5% - 10%)
        profit_pct = max(0.5, min(profit_pct, 10.0))
        
        return profit_pct
    
    def _calculate_costs(self, entry_price: float, sl_price: float, 
                        expected_profit_pct: float) -> Dict[str, float]:
        """
        Рассчитывает все затраты на сделку.
        
        Returns:
            {
                'commission': float,  # Комиссия (%)
                'spread': float,      # Спред (%)
                'slippage': float,    # Проскальзывание (%)
                'total': float        # Общие затраты (%)
            }
        """
        # Комиссия (вход + выход)
        commission = self.params['commission_rate'] * 2
        
        # Спред
        spread = self.params['spread_estimate']
        
        # Проскальзывание
        slippage = self.params['slippage_estimate']
        
        total = commission + spread + slippage
        
        return {
            'commission': commission,
            'spread': spread,
            'slippage': slippage,
            'total': total
        }
    
    def _make_decision(self, net_profit_pct: float, risk_reward: float, 
                      sl_distance_pct: float, zone: ProbabilityZone) -> Tuple[str, str]:
        """
        Принимает финальное решение: OPEN или HOLD.
        
        Returns:
            (decision, reasoning)
        """
        reasons = []
        
        # Проверка 1: Чистая прибыль
        if net_profit_pct < self.params['min_net_profit_pct']:
            return 'HOLD', f"Net profit {net_profit_pct:.2f}% < min {self.params['min_net_profit_pct']}%"
        reasons.append(f"net_profit={net_profit_pct:.2f}%")
        
        # Проверка 2: Risk/Reward
        if risk_reward < self.params['risk_reward_min']:
            return 'HOLD', f"R/R {risk_reward:.2f} < min {self.params['risk_reward_min']}"
        reasons.append(f"R/R={risk_reward:.2f}")
        
        # Проверка 3: SL не слишком далеко
        if sl_distance_pct > self.params['max_sl_distance_pct']:
            return 'HOLD', f"SL distance {sl_distance_pct:.2f}% > max {self.params['max_sl_distance_pct']}%"
        reasons.append(f"SL={sl_distance_pct:.2f}%")
        
        # Проверка 4: Вероятность зоны
        if zone.probability < self.params['min_probability_threshold']:
            return 'HOLD', f"Zone probability {zone.probability:.2f} < threshold {self.params['min_probability_threshold']}"
        reasons.append(f"prob={zone.probability:.2f}")
        
        # Все проверки пройдены
        reasoning = f"All checks passed: {', '.join(reasons)}, scenario={zone.scenario.value}"
        return 'OPEN', reasoning
    
    def _hold_decision(self, reason: str) -> Dict[str, Any]:
        """
        Возвращает решение HOLD с причиной.
        """
        return {
            'decision': 'HOLD',
            'reasoning': reason,
            'trade_direction': None,
            'entry_price': 0.0,
            'sl_price': 0.0,
            'sl_distance_pct': 0.0,
            'expected_profit_pct': 0.0,
            'net_profit_pct': 0.0,
            'risk_reward': 0.0,
            'costs': {'commission': 0.0, 'spread': 0.0, 'slippage': 0.0, 'total': 0.0},
            'horizon_minutes': 0,
            'confidence': 0.0,
            'scenario': None
        }
