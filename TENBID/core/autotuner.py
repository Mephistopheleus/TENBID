"""
Autotuner Module - Self-learning weight optimization based on historical performance.

Analyzes past trades (real and shadow) to find optimal confidence weights for:
1. Direction prediction (Long/Short)
2. Risk parameters (SL %, Position Size, Trailing sensitivity)

Goal: Maximize WinRate, PnL and minimize Drawdown by adjusting trust in specific analyzers.
"""

import sqlite3
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class TradeContextSnapshot:
    """Snapshot of all inputs at the moment of trade decision."""
    trade_id: str
    timestamp: float
    symbol: str
    side: str  # BUY/SELL
    
    # Analyzer Scores at entry
    btc_correlation: float
    btc_confidence: float
    fractal_score: float
    orderbook_score: float
    pattern_score: float
    regime_score: float
    regime_type: str
    
    # System Weights used
    weights_used: Dict[str, float]
    
    # Decision Parameters
    entry_price: float
    sl_percent: float
    tp_percent: float
    position_size: float
    final_confidence: float
    
    # Outcome
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # 'TP', 'SL', 'MANUAL', 'TRAILING'
    pnl_percent: float = 0.0
    pnl_usdt: float = 0.0
    is_winner: bool = False
    
    # Shadow trade tracking
    is_shadow: bool = False
    shadow_reason: Optional[str] = None  # 'LOW_CONFIDENCE', 'RISK_LIMIT', 'SHADOW_TEST'
    
    # Market Context at Exit
    max_drawdown_during_trade: float = 0.0
    max_profit_during_trade: float = 0.0

class Autotuner:
    def __init__(self, db_path: str = "trade_history.db"):
        self.db_path = db_path
        self.current_weights = self._load_latest_weights()
        self.history_window = 100  # Analyze last N trades
        
    def _get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def _load_latest_weights(self) -> Dict[str, float]:
        """Load the most recent optimized weights from DB."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT weights_json FROM autotuner_logs 
                ORDER BY timestamp DESC LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                weights = json.loads(row[0])
                logger.info(f"Loaded optimized weights: {weights}")
                return weights
        except Exception as e:
            logger.warning(f"Could not load weights, using defaults: {e}")
        finally:
            conn.close()
            
        # Default weights if no history
        return {
            "btc_correlation": 1.5,
            "fractal": 1.3,
            "orderbook": 1.2,
            "pattern": 1.4,
            "regime": 2.0,
            "trend": 1.0,
            "sl_aggressiveness": 1.0,  # Multiplier for SL calculation
            "size_confidence": 1.0     # Multiplier for position sizing
        }

    def record_trade_outcome(self, snapshot: TradeContextSnapshot):
        """Save a completed trade context for future analysis (real and shadow trades)."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trade_analysis_log (
                    trade_id, timestamp, symbol, side, 
                    btc_correlation, btc_confidence, fractal_score, orderbook_score, 
                    pattern_score, regime_score, regime_type,
                    weights_used_json, sl_percent, position_size,
                    pnl_percent, pnl_usdt, is_winner, exit_reason,
                    max_drawdown_during_trade, max_profit_during_trade,
                    is_shadow, shadow_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                snapshot.trade_id, snapshot.timestamp, snapshot.symbol, snapshot.side,
                snapshot.btc_correlation, snapshot.btc_confidence, snapshot.fractal_score, snapshot.orderbook_score,
                snapshot.pattern_score, snapshot.regime_score, snapshot.regime_type,
                json.dumps(snapshot.weights_used), snapshot.sl_percent, snapshot.position_size,
                snapshot.pnl_percent, snapshot.pnl_usdt, int(snapshot.is_winner), snapshot.exit_reason,
                snapshot.max_drawdown_during_trade, snapshot.max_profit_during_trade,
                int(snapshot.is_shadow), snapshot.shadow_reason
            ))
            conn.commit()
            trade_type = "SHADOW" if snapshot.is_shadow else "REAL"
            logger.debug(f"Recorded {trade_type} trade outcome for analysis: {snapshot.trade_id} (PnL: {snapshot.pnl_percent}%)")
        except Exception as e:
            logger.error(f"Failed to record trade outcome: {e}")
        finally:
            conn.close()

    def analyze_and_optimize(self) -> Dict[str, float]:
        """
        Core logic: Analyze recent trades to find better weights.
        
        Strategy:
        1. Group trades by 'Regime' and 'Signal Dominance'.
        2. Simulate: What if we trusted the winning signals MORE and losing signals LESS?
        3. Adjust SL logic: If many losses were due to tight SL wick-outs, reduce SL aggressiveness.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # Fetch recent history
            cursor.execute("""
                SELECT * FROM trade_analysis_log 
                ORDER BY timestamp DESC LIMIT ?
            """, (self.history_window,))
            rows = cursor.fetchall()
            
            if len(rows) < 10:
                logger.info("Not enough history for optimization yet.")
                return self.current_weights

            # Convert to objects for easier processing
            history = [self._row_to_snapshot(row) for row in rows]
            
            new_weights = self._calculate_optimal_weights(history)
            
            # Log the update
            self._save_weights(new_weights, len(history))
            
            logger.info(f"Autotuner updated weights based on {len(history)} trades.")
            return new_weights
            
        except Exception as e:
            logger.error(f"Error in autotuner optimization: {e}")
            return self.current_weights
        finally:
            conn.close()

    def _row_to_snapshot(self, row: tuple) -> TradeContextSnapshot:
        # Mapping DB columns to dataclass fields (simplified for brevity)
        # Assuming column order matches insert statement roughly
        return TradeContextSnapshot(
            trade_id=row[1], timestamp=row[2], symbol=row[3], side=row[4],
            btc_correlation=row[5], fractal_score=row[6], orderbook_score=row[7],
            pattern_score=row[8], regime_score=row[9], regime_type=row[10],
            weights_used=json.loads(row[11]), sl_percent=row[12], position_size=row[13],
            pnl_percent=row[14], pnl_usdt=row[15], is_winner=bool(row[16]),
            exit_reason=row[17], max_drawdown_during_trade=row[18], max_profit_during_trade=row[19],
            entry_price=0.0, tp_percent=0.0, exit_price=0.0, final_confidence=0.0 # Missing in simple select, fill defaults
        )

    def _calculate_optimal_weights(self, history: List[TradeContextSnapshot]) -> Dict[str, float]:
        """
        Heuristic optimization algorithm using both real and shadow trades.
        Compares weighted scores of winners vs losers, and evaluates shadow trade quality.
        
        Shadow trades analysis:
        - Prevented losses: shadow trades that would have lost money (good decision to skip)
        - Missed profits: shadow trades that would have won (opportunity cost)
        """
        # Separate real and shadow trades
        real_trades = [t for t in history if not t.is_shadow]
        shadow_trades = [t for t in history if t.is_shadow]
        
        winners = [t for t in real_trades if t.is_winner]
        losers = [t for t in real_trades if not t.is_winner]
        
        # Analyze shadow trades for quality assessment
        shadow_prevented_losses = [t for t in shadow_trades if not t.is_winner]  # Good: we avoided a loss
        shadow_missed_wins = [t for t in shadow_trades if t.is_winner]  # Bad: we missed a profit
        
        if not winners and not losers:
            return self.current_weights

        # 1. Analyze Signal Strength Differences (Real Trades)
        avg_winner_scores = self._avg_scores(winners) if winners else {}
        avg_loser_scores = self._avg_scores(losers) if losers else {}
        
        new_weights = self.current_weights.copy()
        
        # Adjust Analyzer Weights based on correlation with winning
        for key in ['btc_correlation', 'fractal_score', 'orderbook_score', 'pattern_score', 'regime_score']:
            w_diff = avg_winner_scores.get(key, 0) - avg_loser_scores.get(key, 0)
            current_w = new_weights.get(key.replace('_score', ''), 1.0)
            
            # If winners had significantly higher score in this metric, increase weight
            if w_diff > 0.15:
                new_weights[key.replace('_score', '')] = current_w * 1.08
            elif w_diff < -0.15:
                new_weights[key.replace('_score', '')] = current_w * 0.92
        
        # 2. PnL-Weighted Analysis (not just win/loss)
        if winners:
            avg_winner_pnl = np.mean([t.pnl_percent for t in winners])
            avg_loser_pnl = np.mean([abs(t.pnl_percent) for t in losers]) if losers else 0
            
            # If average winner is much bigger than average loser, we're on right track
            if avg_winner_pnl > avg_loser_pnl * 1.5:
                logger.info(f"Strong R/R ratio: Winners {avg_winner_pnl:.2f}% vs Losers {avg_loser_pnl:.2f}%")
                # Boost weights slightly - strategy is working
                for k in ['regime', 'pattern', 'fractal']:
                    new_weights[k] = min(3.0, new_weights.get(k, 1.0) * 1.03)
        
        # 3. Shadow Trade Quality Analysis
        if shadow_trades:
            shadow_quality_score = len(shadow_prevented_losses) / len(shadow_trades) if shadow_trades else 0
            
            # If shadow trades show we're avoiding many losses, our confidence thresholds are good
            if shadow_quality_score > 0.65:
                logger.info(f"Shadow analysis: {shadow_quality_score*100:.1f}% of skipped trades would have lost. Threshold strategy is effective.")
                # Slightly increase regime weight - our filtering is working
                new_weights['regime'] = min(3.0, new_weights.get('regime', 2.0) * 1.03)
            
            # If we're missing too many wins, maybe we're too conservative
            if len(shadow_missed_wins) > len(shadow_prevented_losses) * 1.2:
                logger.info(f"Shadow analysis: Missing more wins than preventing losses. Consider lowering thresholds.")
                # Slightly reduce sl_aggressiveness to allow more trades
                new_weights['sl_aggressiveness'] = max(0.2, new_weights.get('sl_aggressiveness', 1.0) * 0.97)
        
        # 4. Analyze SL Failures (The "5% SL" problem)
        # Check losers where max_profit_during_trade was positive but hit SL
        false_breakouts = [t for t in losers if t.max_profit_during_trade > 1.0 and t.exit_reason == 'SL']
        if len(false_breakouts) > len(losers) * 0.25: # If 25% of losses were wick-outs
            logger.info(f"Wick-out alert: {len(false_breakouts)}/{len(losers)} losses were false breakouts. Widening SL.")
            new_weights['sl_aggressiveness'] *= 0.88  # Make SL wider
            new_weights['size_confidence'] *= 0.93   # Reduce size slightly to compensate risk
        
        # 5. Consecutive Loss Analysis (Drawdown Control)
        # Check for streaks of losses
        sorted_history = sorted(history, key=lambda x: x.timestamp, reverse=True)
        consecutive_losses = 0
        max_consecutive_losses = 0
        for t in sorted_history:
            if not t.is_shadow and not t.is_winner:
                consecutive_losses += 1
                max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            else:
                consecutive_losses = 0
        
        if max_consecutive_losses >= 4:
            logger.warning(f"Detected {max_consecutive_losses} consecutive losses. Reducing risk exposure.")
            new_weights['size_confidence'] *= 0.85  # Significantly reduce position size
            new_weights['sl_aggressiveness'] *= 0.95  # Slightly tighter SL
        
        # 6. Regime Specific Tuning
        # If we lose often in 'RANGING', reduce weight of Trend indicators in ranging markets
        regime_losers = [t for t in losers if t.regime_type == 'RANGING']
        if len(regime_losers) > len(losers) * 0.35:
            logger.info(f"High loss rate in RANGING ({len(regime_losers)}/{len(losers)}). Reducing trend indicator weights.")
            new_weights['trend'] = max(0.5, new_weights.get('trend', 1.0) * 0.88)
        
        # 7. Pattern-Specific Analysis
        # If pattern analyzer shows high confidence but loses, reduce its weight
        pattern_losers = [t for t in losers if t.pattern_score > 0.7]
        if len(pattern_losers) > len(losers) * 0.3:
            logger.info("Pattern failures detected. Reducing pattern analyzer weight.")
            new_weights['pattern'] = max(0.8, new_weights.get('pattern', 1.4) * 0.9)
        
        # 8. BTC Correlation Analysis
        # If BTC correlation is high but we lose, reduce btc_correlation weight
        btc_losers = [t for t in losers if abs(t.btc_correlation) > 0.7]
        if len(btc_losers) > len(losers) * 0.3:
            logger.info("BTC correlation failures detected. Reducing BTC weight.")
            new_weights['btc_correlation'] = max(0.5, new_weights.get('btc_correlation', 1.5) * 0.9)
        
        # 9. Orderbook Divergence Analysis
        # If orderbook score disagrees with outcome frequently, adjust weight
        ob_wrong = [t for t in real_trades if (t.orderbook_score > 0.5 and not t.is_winner) or 
                                           (t.orderbook_score < -0.5 and t.is_winner)]
        if len(ob_wrong) > len(real_trades) * 0.4:
            logger.info("Orderbook analysis often wrong. Reducing orderbook weight.")
            new_weights['orderbook'] = max(0.5, new_weights.get('orderbook', 1.2) * 0.88)
        
        # 10. Fractal Support/Resistance Quality
        # If fractal levels fail to hold (price goes through SL quickly), adjust
        fractal_failures = [t for t in losers if t.max_drawdown_during_trade > abs(t.pnl_percent) * 1.5]
        if len(fractal_failures) > len(losers) * 0.25:
            logger.info("Fractal levels failing frequently. Reducing fractal weight.")
            new_weights['fractal'] = max(0.6, new_weights.get('fractal', 1.3) * 0.9)
        
        # Clamp weights to reasonable bounds
        for k in new_weights:
            if k != 'sl_aggressiveness' and k != 'size_confidence':
                new_weights[k] = max(0.5, min(3.0, new_weights[k]))
            else:
                new_weights[k] = max(0.2, min(2.0, new_weights[k]))
        
        # Log significant changes
        for k in new_weights:
            old_val = self.current_weights.get(k, 1.0)
            new_val = new_weights[k]
            if abs(new_val - old_val) / old_val > 0.05:  # More than 5% change
                logger.info(f"Weight '{k}': {old_val:.2f} -> {new_val:.2f} ({(new_val/old_val-1)*100:+.1f}%)")

        return new_weights

    def _avg_scores(self, trades: List[TradeContextSnapshot]) -> Dict[str, float]:
        if not trades: return {}
        keys = ['btc_correlation', 'fractal_score', 'orderbook_score', 'pattern_score', 'regime_score']
        sums = {k: 0 for k in keys}
        for t in trades:
            sums['btc_correlation'] += t.btc_correlation
            sums['fractal_score'] += t.fractal_score
            sums['orderbook_score'] += t.orderbook_score
            sums['pattern_score'] += t.pattern_score
            sums['regime_score'] += t.regime_score
            
        count = len(trades)
        return {k: v/count for k, v in sums.items()}

    def integrate_lab_insights(self, lab_results: List[Dict]):
        """
        Интеграция результатов из Shadow Lab.
        Анализирует виртуальные сделки и корректирует веса на основе их успешности.
        
        Args:
            lab_results: Список словарей с результатами симуляций от ShadowLab
        """
        if not lab_results:
            return None
            
        logger.info(f"🧠 Autotuner: Получено {len(lab_results)} инсайтов от Shadow Lab")
        
        # Группируем результаты по гипотезам
        hypothesis_stats = {}
        for res in lab_results:
            hyp_name = res.get('hypothesis_name')
            if hyp_name not in hypothesis_stats:
                hypothesis_stats[hyp_name] = {'wins': 0, 'losses': 0, 'total_pnl': 0.0, 'count': 0}
            
            if res.get('decision') == 'ENTERED':
                pnl = res.get('net_pnl', 0.0)
                hypothesis_stats[hyp_name]['total_pnl'] += pnl
                hypothesis_stats[hyp_name]['count'] += 1
                if pnl > 0:
                    hypothesis_stats[hyp_name]['wins'] += 1
                else:
                    hypothesis_stats[hyp_name]['losses'] += 1
        
        new_weights = self.current_weights.copy()
        changes_made = False
        
        # Анализируем каждую гипотезу
        for hyp_name, stats in hypothesis_stats.items():
            if stats['count'] < 3:  # Нужно минимум 3 сделки для статистики
                continue
                
            win_rate = stats['wins'] / stats['count']
            avg_pnl = stats['total_pnl'] / stats['count']
            
            logger.info(f"Гипотеза [{hyp_name}]: Сделок={stats['count']}, WinRate={win_rate:.2f}, AvgPnL={avg_pnl:.4f}")
            
            # Применяем изменения в зависимости от типа гипотезы
            if hyp_name == "lower_entry_threshold":
                # Если снижение порога дало прибыль - снижаем порог входа
                if win_rate > 0.55 and avg_pnl > 0:
                    logger.info("✅ Гипотеза подтверждена: можно снизить порог входа")
                    new_weights['size_confidence'] = min(2.0, new_weights.get('size_confidence', 1.0) * 1.05)
                    changes_made = True
                elif win_rate < 0.40:
                    logger.info("❌ Гипотеза опровергнута: снижение порога ведет к убыткам")
                    new_weights['size_confidence'] = max(0.5, new_weights.get('size_confidence', 1.0) * 0.95)
                    changes_made = True
                    
            elif hyp_name == "wider_stop_loss":
                # Если широкий стоп улучшил результаты
                if win_rate > 0.50 or avg_pnl > 0.001:
                    logger.info("✅ Широкий стоп улучшает результаты")
                    new_weights['sl_aggressiveness'] = max(0.5, new_weights.get('sl_aggressiveness', 1.0) * 0.95)
                    changes_made = True
                else:
                    logger.info("❌ Широкий стоп не помог")
                    new_weights['sl_aggressiveness'] = min(2.0, new_weights.get('sl_aggressiveness', 1.0) * 1.02)
                    changes_made = True
                    
            elif hyp_name == "tighter_take_profit":
                # Если быстрый тейк лучше
                if win_rate > 0.60:
                    logger.info("✅ Быстрая фиксация прибыли работает")
                    # Можно добавить параметр take_profit_aggressiveness в будущем
                else:
                    logger.info("❌ Ранний выход уменьшает прибыль")
                    
            elif hyp_name == "factor_weight_boost":
                # Если учет слабых факторов помог
                if win_rate > 0.55 and avg_pnl > 0:
                    logger.info("✅ Учет слабых факторов полезен")
                    for key in ['btc_correlation', 'fractal', 'orderbook']:
                        new_weights[key] = min(3.0, new_weights.get(key, 1.0) * 1.03)
                        changes_made = True
            
            # Обработка динамических гипотез вида "boost_{factor_name}_weight"
            elif hyp_name.startswith("boost_") and hyp_name.endswith("_weight"):
                factor_name = hyp_name.replace("boost_", "").replace("_weight", "")
                
                if win_rate > 0.60 and avg_pnl > 0:
                    logger.info(f"✅ Динамическая гипотеза подтверждена: фактор {factor_name} заслуживает повышения веса")
                    
                    # Маппинг имени фактора на ключ в весах
                    weight_key_map = {
                        'btc_correlation': 'btc_correlation',
                        'fractal_score': 'fractal',
                        'orderbook_score': 'orderbook',
                        'pattern_score': 'pattern',
                        'regime_score': 'regime'
                    }
                    
                    weight_key = weight_key_map.get(factor_name, factor_name)
                    if weight_key in new_weights or weight_key in ['btc_correlation', 'fractal', 'orderbook', 'pattern', 'regime']:
                        new_weights[weight_key] = min(3.0, new_weights.get(weight_key, 1.0) * 1.05)
                        changes_made = True
                        logger.info(f"📈 Вес фактора '{weight_key}' увеличен на 5%")
                    else:
                        logger.debug(f"Фактор {factor_name} не найден в весах, пропускаем")
                else:
                    logger.info(f"❌ Динамическая гипотеза для {factor_name} не подтвердилась")
        
        # Сохраняем обновленные веса если были изменения
        if changes_made:
            self.current_weights = new_weights
            self._save_weights(new_weights, len(lab_results), source="shadow_lab")
            logger.info("🎯 Веса обновлены на основе данных Shadow Lab")
            return new_weights
        
        return None

    def _save_weights(self, weights: Dict[str, float], sample_size: int, source: str = "regular"):
        """Сохраняет веса в БД с указанием источника (обычный или из лаборатории)."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO autotuner_logs (timestamp, weights_json, sample_size, source)
                VALUES (?, ?, ?, ?)
            """, (datetime.now().timestamp(), json.dumps(weights), sample_size, source))
            conn.commit()
            logger.debug(f"Weights saved (source: {source})")
        except Exception as e:
            logger.error(f"Failed to save weights: {e}")
        finally:
            conn.close()

    def get_recommendation(self, current_context: Dict) -> Dict[str, float]:
        """
        Return the currently active optimized weights.
        In advanced version, could return dynamic adjustments based on current regime.
        """
        # Here we just return the latest global optimum
        return self.current_weights

# DB Initialization helper
def init_autotuner_db(db_path: str = "trade_history.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trade_analysis_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_id TEXT UNIQUE,
        timestamp REAL,
        symbol TEXT,
        side TEXT,
        btc_correlation REAL,
        btc_confidence REAL,
        fractal_score REAL,
        orderbook_score REAL,
        pattern_score REAL,
        regime_score REAL,
        regime_type TEXT,
        weights_used_json TEXT,
        sl_percent REAL,
        position_size REAL,
        pnl_percent REAL,
        pnl_usdt REAL,
        is_winner INTEGER,
        exit_reason TEXT,
        max_drawdown_during_trade REAL,
        max_profit_during_trade REAL,
        is_shadow INTEGER DEFAULT 0,
        shadow_reason TEXT
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS autotuner_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp REAL,
        weights_json TEXT,
        sample_size INTEGER,
        source TEXT DEFAULT 'regular'
    )
    """)
    
    conn.commit()
    conn.close()
    logger.info("Autotuner database tables initialized.")

if __name__ == "__main__":
    init_autotuner_db()
    print("Autotuner module ready.")
