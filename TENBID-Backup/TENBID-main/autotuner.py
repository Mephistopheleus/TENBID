import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
import math

logger = logging.getLogger(__name__)

class Autotuner:
    def __init__(self, db_path: str = "trade_history.db"):
        self.db_path = db_path
        self.recommendations_cache = {}
        self.last_update = {}
        self.base_weights = {
            "rsi": 1.0, "macd": 1.0, "bb": 1.0, "volatility": 1.0,
            "fractal": 1.0, "regime": 1.0, "volume": 1.0, "orderbook": 1.0
        }
        self.min_samples = 5 
        logger.info("Autotuner initialized with shadow learning support")

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    symbol TEXT, side TEXT, entry_price REAL, exit_price REAL,
                    pnl_percent REAL, pnl_usdt REAL, is_shadow BOOLEAN DEFAULT FALSE,
                    shadow_reason TEXT, regime_type TEXT, confidence_score REAL,
                    weights_snapshot TEXT, parameters_snapshot TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS weight_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    regime_type TEXT, indicator_name TEXT, old_weight REAL,
                    new_weight REAL, reason TEXT, sample_count INTEGER
                )
            """)
            conn.commit()
            logger.info("Database schema verified/created successfully")
        except Exception as e:
            logger.error(f"DB Init Error: {e}")
            raise
        finally:
            conn.close()

    def record_trade(self, trade_data: Dict[str, Any]):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trades (symbol, side, entry_price, exit_price, pnl_percent, pnl_usdt,
                    is_shadow, shadow_reason, regime_type, confidence_score, weights_snapshot, parameters_snapshot)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_data.get('symbol'), trade_data.get('side'), trade_data.get('entry_price'),
                trade_data.get('exit_price'), trade_data.get('pnl_percent'), trade_data.get('pnl_usdt'),
                trade_data.get('is_shadow', False), trade_data.get('shadow_reason'),
                trade_data.get('regime_type'), trade_data.get('confidence_score'),
                json.dumps(trade_data.get('weights', {})), json.dumps(trade_data.get('parameters', {}))
            ))
            conn.commit()
        except Exception as e:
            logger.error(f"Error recording trade: {e}")
        finally:
            conn.close()

    def analyze_performance(self, regime_type: str = "ALL") -> Dict[str, Any]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            base_query = "SELECT * FROM trades WHERE 1=1"
            params = []
            if regime_type != "ALL":
                base_query += " AND regime_type = ?"
                params.append(regime_type)
            cursor.execute(base_query, params)
            rows = cursor.fetchall()
            
            if not rows: return {"status": "no_data", "sample_count": 0}

            total_real, total_shadow, real_wins, real_losses = 0, 0, 0, 0
            shadow_wins, shadow_losses, sum_pnl_real, sum_pnl_shadow = 0, 0, 0.0, 0.0
            weight_effects = defaultdict(lambda: {"wins": 0, "losses": 0, "total_impact": 0.0})

            for row in rows:
                is_shadow = bool(row['is_shadow'])
                pnl = row['pnl_percent'] or 0.0
                weights = json.loads(row['weights_snapshot'] or "{}")
                
                if is_shadow:
                    total_shadow += 1
                    if pnl < 0: shadow_wins += 1; sum_pnl_shadow += abs(pnl)
                    else: shadow_losses += 1; sum_pnl_shadow -= pnl
                else:
                    total_real += 1
                    if pnl > 0: real_wins += 1
                    else: real_losses += 1
                    sum_pnl_real += pnl
                    for ind, w in weights.items():
                        if ind in self.base_weights:
                            weight_effects[ind]["total_impact"] += w * pnl
                            if pnl > 0: weight_effects[ind]["wins"] += 1
                            else: weight_effects[ind]["losses"] += 1

            winrate_real = (real_wins / total_real * 100) if total_real > 0 else 0.0
            avg_pnl_real = (sum_pnl_real / total_real) if total_real > 0 else 0.0
            shadow_efficiency = (shadow_wins / total_shadow * 100) if total_shadow > 0 else 0.0
            
            return {
                "status": "ok", "sample_count": total_real + total_shadow,
                "real_trades": total_real, "shadow_trades": total_shadow,
                "real_winrate": winrate_real, "real_avg_pnl": avg_pnl_real,
                "shadow_efficiency": shadow_efficiency, "net_shadow_pnl": sum_pnl_shadow,
                "weight_effects": dict(weight_effects)
            }
        except Exception as e:
            logger.error(f"Analysis error: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            conn.close()

    def get_recommendation(self, context: Dict[str, Any]) -> Dict[str, float]:
        regime = context.get("regime_type", "ALL")
        now = datetime.now()
        cache_key = f"{regime}"
        
        if cache_key in self.recommendations_cache:
            last_time, data = self.recommendations_cache[cache_key]
            if (now - last_time).total_seconds() < 300:
                return data

        stats = self.analyze_performance(regime)
        
        if stats["status"] == "no_data" or stats["sample_count"] < self.min_samples:
            rec = self.base_weights.copy()
            for k in rec: rec[k] *= (1.0 + (hash(str(now) + k) % 100) / 1000.0) 
            self.recommendations_cache[cache_key] = (now, rec)
            return rec

        new_weights = self.base_weights.copy()
        weight_effects = stats.get("weight_effects", {})
        logger.info(f"Autotuner optimizing for {regime}. Real: {stats['real_trades']}, Shadow: {stats['shadow_trades']}")

        for indicator, effects in weight_effects.items():
            if effects["wins"] + effects["losses"] == 0: continue
            success_rate = effects["wins"] / (effects["wins"] + effects["losses"])
            avg_impact = effects["total_impact"] / (effects["wins"] + effects["losses"])
            
            if avg_impact > 0.1: 
                factor = 1.0 + (success_rate - 0.5) * 0.2
                new_weights[indicator] = min(2.0, max(0.5, self.base_weights[indicator] * factor))
            elif avg_impact < -0.1:
                factor = 1.0 - (0.5 - success_rate) * 0.2
                new_weights[indicator] = min(2.0, max(0.5, self.base_weights[indicator] * factor))

        self._log_weight_changes(regime, new_weights, stats["sample_count"])
        result = new_weights
        self.recommendations_cache[cache_key] = (now, result)
        return result

    def _log_weight_changes(self, regime: str, new_weights: Dict[str, float], sample_count: int):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            for ind, new_w in new_weights.items():
                old_w = self.base_weights.get(ind, 1.0)
                if abs(old_w - new_w) > 0.01:
                    cursor.execute("""
                        INSERT INTO weight_history (regime_type, indicator_name, old_weight, new_weight, reason, sample_count)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (regime, ind, old_w, new_w, "Auto-optimization", sample_count))
                    self.base_weights[ind] = new_w
            conn.commit()
        except Exception as e:
            logger.error(f"Error logging weight changes: {e}")
        finally:
            conn.close()
