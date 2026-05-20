"""
Shadow Lab Module - Параллельный анализатор альтернативных сценариев
Работает асинхронно, анализируя исторические снимки из БД.
Проверяет гипотезы: "Что если бы мы торговали с другими параметрами?"
"""

import sqlite3
import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import json

# Настройка логгирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ShadowLab")

@dataclass
class LabHypothesis:
    """Гипотеза для проверки в лаборатории"""
    name: str
    param_changes: Dict[str, float]  # Какие параметры меняем (порог, стоп, тейк и т.д.)
    description: str

class ShadowLab:
    def __init__(self, db_path: str = "trade_history.db", low_weight_threshold: float = 0.25):
        self.db_path = db_path
        self.low_weight_threshold = low_weight_threshold  # Порог для "слабых" факторов
        self.is_running = False
        self.results_buffer = []  # Буфер результатов для передачи в автотюнер
        
        # Weak factors buffer from Shadow Calculator (for dynamic hypothesis generation)
        self.weak_factors_from_calculator = []
        
        # Динамические гипотезы генерируются на основе данных
        # Базовый набор остается, но добавляется анализ всех слабых факторов
        self.hypotheses = [
            LabHypothesis(
                name="lower_entry_threshold",
                param_changes={"entry_threshold": 0.55},
                description="Тест снижения порога входа для захвата большего количества сделок"
            ),
            LabHypothesis(
                name="wider_stop_loss",
                param_changes={"stop_loss_multiplier": 1.5},
                description="Тест более широкого стопа для избегания шумовых выбиваний"
            ),
            LabHypothesis(
                name="tighter_take_profit",
                param_changes={"take_profit_multiplier": 0.8},
                description="Тест быстрого фиксирования прибыли"
            ),
            LabHypothesis(
                name="factor_weight_boost",
                param_changes={"min_factor_confidence": 0.15},
                description="Тест учета более слабых факторов влияния"
            )
        ]
    
    def receive_weak_factors(self, weak_factors_data: List[Dict]):
        """
        Receive weak factors data from Shadow Calculator for analysis.
        
        Args:
            weak_factors_data: List of weak factor observations from shadow_calculator
        """
        if weak_factors_data:
            self.weak_factors_from_calculator.extend(weak_factors_data)
            logger.info(f"🔬 Shadow Lab received {len(weak_factors_data)} weak factor observations")
    
    def fetch_all_trades_for_analysis(self, limit: int = 100) -> List[Dict]:
        """
        Загружает ВСЕ сделки (реальные и теневые) для анализа.
        Особое внимание уделяется сделкам, где какие-то факторы имели вес < порога.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Выбираем последние сделки из trade_analysis_log (включая shadow trades)
            # Эта таблица содержит полные снимки с факторами и весами
            query = """
                SELECT * FROM trade_analysis_log 
                ORDER BY timestamp DESC 
                LIMIT ?
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            conn.close()
            
            trades = [dict(row) for row in rows]
            
            # Фильтруем сделки, где есть слабые факторы
            relevant_trades = []
            for trade in trades:
                # Извлекаем факторы из полей btc_correlation, fractal_score и т.д.
                factors = {
                    'btc_correlation': trade.get('btc_correlation', 0),
                    'fractal_score': trade.get('fractal_score', 0),
                    'orderbook_score': trade.get('orderbook_score', 0),
                    'pattern_score': trade.get('pattern_score', 0),
                    'regime_score': trade.get('regime_score', 0)
                }
                
                # Проверяем, есть ли факторы с низким весом
                has_low_weight_factors = any(
                    abs(value) < self.low_weight_threshold and abs(value) > 0.05
                    for value in factors.values() if isinstance(value, (int, float))
                )
                
                # Берем сделку если:
                # 1. Есть слабые факторы (для их анализа)
                # 2. Или это HOLD с уверенностью > 0.4 (упущенные возможности)
                # 3. Или это реальная сделка (для калибровки)
                is_shadow = trade.get('is_shadow', False)
                pnl = trade.get('pnl_percent', 0) or trade.get('pnl_usdt', 0)
                
                if (has_low_weight_factors or 
                    (is_shadow and pnl is not None) or
                    (not is_shadow and pnl is not None)):
                    relevant_trades.append(trade)
            
            logger.info(f"Найдено {len(relevant_trades)} релевантных сделок для анализа (из {len(trades)})")
            return relevant_trades
            
        except Exception as e:
            logger.error(f"Ошибка чтения БД в лаборатории: {e}")
            return []

    def simulate_trade(self, snapshot_data: Dict, hypothesis: LabHypothesis) -> Dict[str, Any]:
        """
        Симулирует исход сделки на основе снимка и измененных параметров гипотезы.
        Возвращает результат: profit, success, reason.
        """
        # Парсим исходные данные снимка
        # snapshot_data ожидается как JSON строка или dict с ключами:
        # entry_price, exit_price, commission, spread, slippage, factors_json
        
        try:
            if isinstance(snapshot_data.get('factors'), str):
                factors = json.loads(snapshot_data['factors'])
            else:
                factors = snapshot_data.get('factors', {})
            
            original_confidence = float(snapshot_data.get('total_confidence', 0.0))
            entry_price = float(snapshot_data.get('simulated_entry_price', 0.0))
            
            # Если цены нет в явном виде (так как сделка не состоялась), 
            # нам нужно реконструировать потенциальный вход на основе текущих рыночных данных в момент снимка.
            # Для упрощения пока берем mid_price из снимка, если он есть, иначе пропускаем.
            if entry_price == 0.0:
                # Пытаемся восстановить из контекста, если есть best_bid/ask
                bid = float(snapshot_data.get('best_bid', 0))
                ask = float(snapshot_data.get('best_ask', 0))
                if bid and ask:
                    entry_price = (bid + ask) / 2
                else:
                    return {"status": "skipped", "reason": "no_price_data"}

            # Применяем параметры гипотезы
            new_threshold = hypothesis.param_changes.get('entry_threshold', 0.713)
            
            # Логика симуляции:
            # 1. Проверяем, проходит ли уверенность по новому порогу
            if original_confidence < new_threshold:
                # Все еще не входим
                return {
                    "hypothesis_name": hypothesis.name,
                    "decision": "NO_ENTRY",
                    "profit": 0.0,
                    "reason": f"Confidence {original_confidence:.3f} < new threshold {new_threshold}"
                }
            
            # 2. Если входим, рассчитываем результат
            # Здесь нужна эмуляция выхода. В реальном режиме теневик ждет выхода.
            # В лаборатории мы можем посмотреть forward на N свечей, но это сложно без доступа к будущему в этом методе.
            # УПРОЩЕНИЕ: Мы используем данные, которые теневик уже собрал о том, "что случилось потом", 
            # если они сохранены в расширенном снимке. 
            # Пока вернем заглушку, предполагающую, что выход произошел по стандартному алгоритму.
            
            # Допустим, у нас есть поле 'simulated_outcome' в БД, которое теневик заполняет постфактум
            # Если его нет, значит сделка еще не закрыта или данные неполные.
            outcome = snapshot_data.get('simulated_outcome') 
            if outcome is None:
                 # Если исхода нет, считаем сделку "открытой" или пропускаем для чистоты эксперимента
                 return {"status": "skipped", "reason": "outcome_not_realized_yet"}

            # Парсим исход
            if isinstance(outcome, str):
                outcome_data = json.loads(outcome)
            else:
                outcome_data = outcome
                
            final_price = float(outcome_data.get('exit_price', entry_price))
            side = snapshot_data.get('side', 'LONG')
            
            # Расчет PnL с учетом новых параметров (например, измененного SL/TP)
            # Это требует сложной логики пересчета пути цены, пока используем фактический исход теневика
            # но с поправкой на комиссии/спред если гипотеза их меняет
            
            gross_pnl = (final_price - entry_price) if side == 'LONG' else (entry_price - final_price)
            # Нормализация к процентам или USDT (зависит от базы)
            # Для простоты считаем в ценах
            
            commission_rate = float(hypothesis.param_changes.get('commission_override', 0.0004)) # Taker default
            cost = entry_price * commission_rate * 2 # Entry + Exit
            
            net_pnl = gross_pnl - cost
            
            return {
                "hypothesis_name": hypothesis.name,
                "decision": "ENTERED",
                "entry_price": entry_price,
                "exit_price": final_price,
                "net_pnl": net_pnl,
                "original_confidence": original_confidence,
                "reason": f"Entered with threshold {new_threshold}"
            }

        except Exception as e:
            logger.error(f"Ошибка симуляции гипотезы {hypothesis.name}: {e}")
            return {"status": "error", "reason": str(e)}

    async def run_cycle(self):
        """Один цикл работы лаборатории"""
        logger.info("🔬 Shadow Lab: Запуск анализа всех сделок и слабых факторов...")
        
        # Загружаем все релевантные сделки (реальные, теневые, HOLD со слабыми факторами)
        all_trades = self.fetch_all_trades_for_analysis(limit=50)
        if not all_trades:
            logger.debug("Нет подходящих сделок для анализа в лаборатории.")
            return []
        
        local_results = []
        
        # Для каждой сделки проверяем все гипотезы
        for trade in all_trades:
            for hyp in self.hypotheses:
                result = self.simulate_trade(trade, hyp)
                if result.get('status') != 'skipped' and result.get('status') != 'error':
                    local_results.append(result)
                    if result.get('decision') == 'ENTERED':
                        logger.debug(f"Гипотеза [{hyp.name}]: {result.get('decision')} | PnL: {result.get('net_pnl', 0):.4f}")
        
        # Генерируем динамические гипотезы на основе слабых факторов
        dynamic_hypotheses = self._generate_dynamic_hypotheses(all_trades)
        for trade in all_trades:
            for dyn_hyp in dynamic_hypotheses:
                result = self.simulate_trade(trade, dyn_hyp)
                if result.get('status') != 'skipped' and result.get('status') != 'error':
                    local_results.append(result)
                    if result.get('decision') == 'ENTERED':
                        logger.debug(f"Динамическая гипотеза [{dyn_hyp.name}]: {result.get('decision')} | PnL: {result.get('net_pnl', 0):.4f}")
        
        if local_results:
            self.results_buffer.extend(local_results)
            logger.info(f"🔬 Shadow Lab: Обработано {len(local_results)} виртуальных сделок (базовые + динамические гипотезы).")
        else:
            logger.info("🔬 Shadow Lab: Нет завершенных симуляций в этом цикле.")
            
        return local_results
    
    def _generate_dynamic_hypotheses(self, trades: List[Dict]) -> List[LabHypothesis]:
        """
        Генерирует гипотезы на основе анализа слабых факторов в предоставленных сделках.
        Если какой-то фактор (например, btc_correlation) часто был в диапазоне 0.1-0.25
        и сделки с ним были бы прибыльными - создаем гипотезу о повышении его веса.
        
        Также использует weak_factors_from_calculator для генерации дополнительных гипотез.
        """
        factor_stats = {}
        
        # Process trades from DB (existing logic)
        for trade in trades:
            factors = json.loads(trade.get('factors', '{}')) if isinstance(trade.get('factors'), str) else trade.get('factors', {})
            decision = trade.get('decision', 'HOLD')
            
            # Нам нужны данные о том, что произошло после (для HOLD это simulated_outcome)
            outcome = trade.get('simulated_outcome')
            if outcome:
                if isinstance(outcome, str):
                    outcome_data = json.loads(outcome)
                else:
                    outcome_data = outcome
                
                # Определяем, была бы сделка прибыльной
                would_be_winner = outcome_data.get('net_pnl', 0) > 0 if isinstance(outcome_data, dict) else False
            else:
                continue  # Пропускаем, если нет исхода
            
            # Анализируем каждый фактор
            for factor_name, factor_value in factors.items():
                if not isinstance(factor_value, (int, float)):
                    continue
                    
                abs_value = abs(factor_value)
                
                # Нас интересуют только слабые факторы (в диапазоне порога)
                if 0.05 < abs_value < self.low_weight_threshold:
                    if factor_name not in factor_stats:
                        factor_stats[factor_name] = {'wins': 0, 'losses': 0, 'count': 0}
                    
                    factor_stats[factor_name]['count'] += 1
                    if would_be_winner:
                        factor_stats[factor_name]['wins'] += 1
                    else:
                        factor_stats[factor_name]['losses'] += 1
        
        # ALSO process weak factors from Shadow Calculator (NEW)
        for weak_obs in self.weak_factors_from_calculator:
            trade_id = weak_obs.get('trade_id', 'unknown')
            total_confidence = weak_obs.get('total_confidence', 0)
            weak_factors = weak_obs.get('weak_factors', {})
            
            for factor_name, factor_value in weak_factors.items():
                if factor_name not in factor_stats:
                    factor_stats[factor_name] = {'wins': 0, 'losses': 0, 'count': 0}
                
                factor_stats[factor_name]['count'] += 1
                # We don't know the outcome yet for fresh observations, 
                # but we track them for pattern detection
                # Outcome will be determined when forbidden trade completes
        
        # Создаем гипотезы для факторов с хорошей статистикой
        dynamic_hyps = []
        for factor_name, stats in factor_stats.items():
            if stats['count'] >= 3:  # Минимум 3 наблюдения
                win_rate = stats['wins'] / stats['count'] if stats['count'] > 0 else 0
                
                if win_rate > 0.60:  # Если фактор в 60%+ случаев приводил к прибыли
                    hyp_name = f"boost_{factor_name}_weight"
                    dynamic_hyps.append(LabHypothesis(
                        name=hyp_name,
                        param_changes={f"factor_{factor_name}_min": 0.15},  # Пример параметра
                        description=f"Тест повышения веса фактора {factor_name} (WinRate={win_rate:.2f})"
                    ))
                    logger.info(f"🧪 Создана динамическая гипотеза: {hyp_name} для фактора {factor_name}")
        
        return dynamic_hyps

    def get_latest_insights(self) -> List[Dict]:
        """Возвращает накопленные инсайты и очищает буфер"""
        if not self.results_buffer:
            return []
        
        insights = self.results_buffer.copy()
        self.results_buffer.clear()
        return insights

    async def start(self, interval: int = 60):
        """Запуск постоянного фонового процесса"""
        self.is_running = True
        logger.info(f"🚀 Shadow Lab запущена. Интервал проверки: {interval} сек.")
        
        while self.is_running:
            try:
                await self.run_cycle()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Критическая ошибка в Shadow Lab: {e}")
                await asyncio.sleep(10) # Пауза перед повтором

    def stop(self):
        self.is_running = False
        logger.info("⏹️ Shadow Lab остановлена.")

# Пример интеграции (не выполняется при импорте)
if __name__ == "__main__":
    lab = ShadowLab()
    # asyncio.run(lab.start())
