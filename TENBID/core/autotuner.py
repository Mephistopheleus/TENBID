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
    exit_price: Optional[float]
    exit_reason: Optional[str]  # 'TP', 'SL', 'MANUAL', 'TRAILING'
    pnl_percent: float
    pnl_usdt: float
    is_winner: bool
    
    # Market Context at Exit
    max_drawdown_during_trade: float
    max_profit_during_trade: float

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
        """Save a completed trade context for future analysis."""
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
                    max_drawdown_during_trade, max_profit_during_trade
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                snapshot.trade_id, snapshot.timestamp, snapshot.symbol, snapshot.side,
                snapshot.btc_correlation, snapshot.btc_confidence, snapshot.fractal_score, snapshot.orderbook_score,
                snapshot.pattern_score, snapshot.regime_score, snapshot.regime_type,
                json.dumps(snapshot.weights_used), snapshot.sl_percent, snapshot.position_size,
                snapshot.pnl_percent, snapshot.pnl_usdt, int(snapshot.is_winner), snapshot.exit_reason,
                snapshot.max_drawdown_during_trade, snapshot.max_profit_during_trade
            ))
            conn.commit()
            logger.debug(f"Recorded trade outcome for analysis: {snapshot.trade_id} (PnL: {snapshot.pnl_percent}%)")
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
        Heuristic optimization algorithm.
        Compares weighted scores of winners vs losers.
        """
        winners = [t for t in history if t.is_winner]
        losers = [t for t in history if not t.is_winner]
        
        if not winners or not losers:
            return self.current_weights

        # 1. Analyze Signal Strength Differences
        avg_winner_scores = self._avg_scores(winners)
        avg_loser_scores = self._avg_scores(losers)
        
        new_weights = self.current_weights.copy()
        
        # Adjust Analyzer Weights based on correlation with winning
        for key in ['btc_correlation', 'fractal_score', 'orderbook_score', 'pattern_score', 'regime_score']:
            w_diff = avg_winner_scores.get(key, 0) - avg_loser_scores.get(key, 0)
            current_w = new_weights.get(key.replace('_score', ''), 1.0)
            
            # If winners had significantly higher score in this metric, increase weight
            if w_diff > 0.1:
                new_weights[key.replace('_score', '')] = current_w * 1.05
            elif w_diff < -0.1:
                new_weights[key.replace('_score', '')] = current_w * 0.95
                
        # 2. Analyze SL Failures (The "5% SL" problem)
        # Check losers where max_profit_during_trade was positive but hit SL
        false_breakouts = [t for t in losers if t.max_profit_during_trade > 1.0 and t.exit_reason == 'SL']
        if len(false_breakouts) > len(losers) * 0.3: # If 30% of losses were wick-outs
            logger.info("Detected frequent SL wick-outs. Reducing SL aggressiveness.")
            new_weights['sl_aggressiveness'] *= 0.9  # Make SL wider
            new_weights['size_confidence'] *= 0.95   # Reduce size slightly to compensate risk

        # 3. Regime Specific Tuning
        # If we lose often in 'RANGING', reduce weight of Trend indicators in ranging markets
        # (Simplified here, ideally would be a matrix of weights per regime)
        
        # Clamp weights to reasonable bounds
        for k in new_weights:
            if k != 'sl_aggressiveness' and k != 'size_confidence':
                new_weights[k] = max(0.5, min(3.0, new_weights[k]))
            else:
                new_weights[k] = max(0.2, min(2.0, new_weights[k]))

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

    def _save_weights(self, weights: Dict[str, float], sample_size: int):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO autotuner_logs (timestamp, weights_json, sample_size)
                VALUES (?, ?, ?)
            """, (datetime.now().timestamp(), json.dumps(weights), sample_size))
            conn.commit()
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
        max_profit_during_trade REAL
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS autotuner_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp REAL,
        weights_json TEXT,
        sample_size INTEGER
    )
    """)
    
    conn.commit()
    conn.close()
    logger.info("Autotuner database tables initialized.")

if __name__ == "__main__":
    init_autotuner_db()
    print("Autotuner module ready.")
