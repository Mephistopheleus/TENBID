"""SQLite database for storing trade history and signals"""
import sqlite3
import json
from datetime import datetime

class HistoryDB:
    def __init__(self, db_path='trade_history.db'):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_tables()
    
    def _init_tables(self):
        cursor = self.conn.cursor()
        
        # Signals table - stores all decisions (open/hold)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                cycle INTEGER,
                confidence REAL,
                threshold REAL,
                decision TEXT,
                reason TEXT,
                price_current REAL,
                position_pct REAL,
                sl_pct REAL,
                tp_pct REAL,
                rr_ratio REAL,
                analysis_json TEXT,
                shadow_result_json TEXT
            )
        ''')
        
        # Trades table - stores actual executed trades
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER,
                open_time TEXT,
                close_time TEXT,
                side TEXT,
                entry_price REAL,
                exit_price REAL,
                sl_price REAL,
                tp_price REAL,
                position_size REAL,
                pnl_usdt REAL,
                pnl_pct REAL,
                status TEXT,
                exit_reason TEXT,
                FOREIGN KEY (signal_id) REFERENCES signals(id)
            )
        ''')
        
        # Shadow tests table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shadow_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                test_type TEXT,
                parameters_json TEXT,
                result_json TEXT,
                recommendation_change INTEGER
            )
        ''')
        
        self.conn.commit()
    
    def log_signal(self, signal_data):
        cursor = self.conn.cursor()
        
        analysis_json = json.dumps(signal_data.get('analysis', {}))
        shadow_json = json.dumps(signal_data.get('shadow_result', {}))
        
        cursor.execute('''
            INSERT INTO signals (
                timestamp, cycle, confidence, threshold, decision, reason,
                price_current, position_pct, sl_pct, tp_pct, rr_ratio,
                analysis_json, shadow_result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            signal_data.get('timestamp'),
            signal_data.get('cycle'),
            signal_data.get('confidence'),
            signal_data.get('threshold'),
            signal_data.get('decision'),
            signal_data.get('reason'),
            signal_data.get('prices', {}).get('current', 0),
            signal_data.get('position', {}).get('position_pct'),
            signal_data.get('position', {}).get('sl_pct'),
            signal_data.get('position', {}).get('tp_pct'),
            signal_data.get('position', {}).get('rr_ratio'),
            analysis_json,
            shadow_json
        ))
        
        self.conn.commit()
        return cursor.lastrowid
    
    def log_trade(self, trade_data):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO trades (
                signal_id, open_time, close_time, side, entry_price, exit_price,
                sl_price, tp_price, position_size, pnl_usdt, pnl_pct, status, exit_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            trade_data.get('signal_id'),
            trade_data.get('open_time'),
            trade_data.get('close_time'),
            trade_data.get('side'),
            trade_data.get('entry_price'),
            trade_data.get('exit_price'),
            trade_data.get('sl_price'),
            trade_data.get('tp_price'),
            trade_data.get('position_size'),
            trade_data.get('pnl_usdt'),
            trade_data.get('pnl_pct'),
            trade_data.get('status'),
            trade_data.get('exit_reason')
        ))
        self.conn.commit()
        return cursor.lastrowid
    
    def log_shadow_test(self, test_data):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO shadow_tests (timestamp, test_type, parameters_json, result_json, recommendation_change)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            test_data.get('timestamp'),
            test_data.get('test_type'),
            json.dumps(test_data.get('parameters', {})),
            json.dumps(test_data.get('result', {})),
            test_data.get('recommendation_change', 0)
        ))
        self.conn.commit()
    
    def get_all_signals(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM signals ORDER BY timestamp DESC')
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def get_all_trades(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM trades ORDER BY open_time DESC')
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def get_statistics(self):
        cursor = self.conn.cursor()
        
        # Total signals
        cursor.execute('SELECT COUNT(*) FROM signals')
        total_signals = cursor.fetchone()[0]
        
        # Hold vs Open decisions
        cursor.execute("SELECT decision, COUNT(*) FROM signals GROUP BY decision")
        decisions = dict(cursor.fetchall())
        
        # Trade statistics
        cursor.execute('''
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN pnl_usdt < 0 THEN 1 ELSE 0 END) as losing_trades,
                SUM(pnl_usdt) as total_pnl,
                AVG(pnl_pct) as avg_pnl_pct
            FROM trades WHERE status = 'CLOSED'
        ''')
        trade_stats = cursor.fetchone()
        
        # Forbidden trades with hypothetical results
        cursor.execute('''
            SELECT COUNT(*), AVG(confidence), AVG(position_pct)
            FROM signals WHERE decision = 'HOLD'
        ''')
        hold_stats = cursor.fetchone()
        
        return {
            'total_signals': total_signals,
            'decisions': decisions,
            'trades': {
                'total': trade_stats[0] or 0,
                'winning': trade_stats[1] or 0,
                'losing': trade_stats[2] or 0,
                'total_pnl': trade_stats[3] or 0.0,
                'avg_pnl_pct': trade_stats[4] or 0.0
            },
            'holds': {
                'count': hold_stats[0] or 0,
                'avg_confidence': hold_stats[1] or 0.0
            }
        }
    
    def close(self):
        self.conn.close()
