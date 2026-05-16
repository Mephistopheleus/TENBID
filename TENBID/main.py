"""
TENBID - Advanced Scalping Trading System for Binance
Complete modular architecture with shadow calculations and adaptive confidence

ИСПРАВЛЕНИЯ:
- Добавлен менеджер позиций для отслеживания активных сделок
- Реализовано закрытие сделок по TP/SL/trailing
- Autotuner получает данные о результатах сделок
- Исправлены конфликты импортов
"""

import asyncio
import logging
from datetime import datetime
from core.config_loader import ConfigLoader
from core.logger import setup_logger
from core.history_db import HistoryDB
from core.binance_connector import BinanceConnector
from analyzers.data_manager import DataManager
from analyzers.synthetic_timeframes import SyntheticTimeframes
from analyzers.market_analyzer import MarketAnalyzer
from analyzers.btc_correlation import BTCCorrelationAnalyzer
from analyzers.fractal_analysis import FractalAnalyzer
from analyzers.orderbook_analysis import OrderbookAnalyzer
from analyzers.pattern_recognition import PatternRecognitionAnalyzer
from analyzers.market_regime import MarketRegimeAnalyzer
from core.analysis_context import AnalysisContext
from confidence.confidence_system import ConfidenceSystem
from trading.position_sizer import PositionSizer
from trading.smart_trailing import SmartTrailing
from shadow.shadow_calculator import ShadowCalculator
from core.autotuner import Autotuner, init_autotuner_db, TradeContextSnapshot
from reports.reporter import Reporter


class PositionManager:
    """Управление активными позициями"""
    
    def __init__(self):
        self.active_positions = {}  # {trade_id: position_info}
        self.position_snapshots = {}  # {trade_id: snapshot}
    
    def add_position(self, trade_id: str, position_info: dict, snapshot: dict):
        """Добавить новую позицию"""
        self.active_positions[trade_id] = {
            'entry_price': position_info['entry_price'],
            'side': position_info.get('side', 'BUY'),
            'sl_price': position_info.get('sl_price'),
            'tp_price': position_info.get('tp_price'),
            'position_pct': position_info['position_pct'],
            'entry_time': datetime.now(),
            'high_since_entry': position_info['entry_price'],
            'low_since_entry': position_info['entry_price']
        }
        self.position_snapshots[trade_id] = snapshot
    
    def update_price(self, trade_id: str, current_price: float):
        """Обновить цену для позиции"""
        if trade_id in self.active_positions:
            pos = self.active_positions[trade_id]
            if current_price > pos['high_since_entry']:
                pos['high_since_entry'] = current_price
            if current_price < pos['low_since_entry']:
                pos['low_since_entry'] = current_price
    
    def remove_position(self, trade_id: str):
        """Удалить позицию"""
        if trade_id in self.active_positions:
            del self.active_positions[trade_id]
        if trade_id in self.position_snapshots:
            del self.position_snapshots[trade_id]
    
    def get_active_count(self) -> int:
        """Количество активных позиций"""
        return len(self.active_positions)


async def main():
    # Setup
    config = ConfigLoader('config.ini')
    setup_logger(config)
    logger = logging.getLogger('TENBID')
    
    logger.info("="*60)
    logger.info("TENBID - Advanced Scalping System Starting...")
    logger.info(f"Mode: {config.get('GENERAL', 'mode')}")
    logger.info(f"Symbol: {config.get('GENERAL', 'symbol')}")
    logger.info(f"Initial Balance: {config.get('GENERAL', 'initial_balance')} USDT")
    logger.info("="*60)
    
    # Initialize components
    db = HistoryDB()
    init_autotuner_db()  # Initialize Autotuner tables
    binance = BinanceConnector(config)
    data_mgr = DataManager(config, binance)
    synth_tf = SyntheticTimeframes(config)
    market_analyzer = MarketAnalyzer(config)
    btc_correlation = BTCCorrelationAnalyzer(binance)
    fractal_analyzer = FractalAnalyzer()
    orderbook_analyzer = OrderbookAnalyzer(binance)
    pattern_analyzer = PatternRecognitionAnalyzer()
    market_regime_analyzer = MarketRegimeAnalyzer()
    confidence_sys = ConfidenceSystem(config)
    position_sizer = PositionSizer(config)
    trailing = SmartTrailing(config)
    shadow = ShadowCalculator(config, db)
    autotuner = Autotuner()  # Initialize Autotuner
    reporter = Reporter(db, config)
    position_manager = PositionManager()  # Менеджер позиций
    
    # Connect to Binance
    await binance.connect()
    logger.info("Connected to Binance API")
    
    # Warmup - load historical data
    logger.info(f"Warming up with {config.getint('DATA', 'warmup_candles')} candles...")
    candles, base_lineage = await data_mgr.load_warmup_data()
    logger.info(f"Loaded {len(candles)} base candles with lineage: {base_lineage.source.value}")
    
    # Build synthetic timeframes
    synth_data = synth_tf.build_all(candles, base_lineage)
    logger.info(f"Built {len(synth_data)} synthetic timeframes with lineage tracking")
    
    # Main trading loop
    cycle_count = 0
    last_report_time = datetime.now()
    
    try:
        while True:
            cycle_start = datetime.now()
            cycle_count += 1
            
            # Fetch new data
            new_candles, new_lineage = await data_mgr.fetch_latest()
            all_data = synth_tf.build_all(new_candles, new_lineage)
            
            # Analyze market
            analysis = market_analyzer.analyze(all_data)
            
            # Создаем контекст анализа
            symbol = config.get('GENERAL', 'symbol')
            base_tf = '5m'
            
            context = AnalysisContext(
                symbol=symbol,
                timeframe=base_tf,
                base_lineage=new_lineage
            )
            
            # Добавляем данные в контекст
            for tf, (df, lineage) in all_data.items():
                if tf == base_tf:
                    context.add_market_data(symbol, df, lineage)
                else:
                    context.add_synthetic_data(tf, df, lineage)
            
            # Запускаем продвинутые анализаторы через контекст
            btc_result = btc_correlation.analyze(symbol, context)
            fractal_result = fractal_analyzer.analyze(symbol, context)
            orderbook_result = orderbook_analyzer.analyze(symbol, context)
            pattern_result = pattern_analyzer.analyze(context)
            regime_result = market_regime_analyzer.analyze(context)
            
            # Get optimized weights from Autotuner FIRST (before calculating confidence)
            optimized_weights = autotuner.get_recommendation({})
            
            # Calculate confidence with weights from Autotuner
            confidence_result = confidence_sys.calculate(
                analysis, all_data, btc_result, fractal_result, 
                orderbook_result, pattern_result, regime_result,
                override_weights=optimized_weights  # Pass weights from Autotuner
            )
            current_confidence = confidence_result['total_confidence']
            score_lineage = confidence_result.get('score_lineage')
            
            # Get adaptive threshold
            threshold = confidence_sys.get_adaptive_threshold(analysis)
            
            # Получаем текущую цену
            current_price = all_data['5m'][0].iloc[-1]['close'] if len(all_data['5m']) > 0 else 0
            
            # === УПРАВЛЕНИЕ АКТИВНЫМИ ПОЗИЦИЯМИ ===
            if position_manager.get_active_count() > 0:
                # Обновляем цены в активных позициях
                for trade_id in list(position_manager.active_positions.keys()):
                    position_manager.update_price(trade_id, current_price)
                    pos = position_manager.active_positions[trade_id]
                    
                    # Проверяем выход по SL
                    if pos['side'] == 'BUY' and current_price <= pos['sl_price']:
                        logger.info(f"[CYCLE_{cycle_count}] CLOSE POSITION {trade_id}: Stop Loss hit at {current_price}")
                        pnl_pct = (current_price - pos['entry_price']) / pos['entry_price'] * 100
                        pnl_usdt = pnl_pct * pos['position_pct'] * config.getfloat('GENERAL', 'initial_balance') / 100
                        
                        # Обновляем snapshot и записываем в Autotuner
                        snapshot = position_manager.position_snapshots[trade_id]
                        snapshot.exit_price = current_price
                        snapshot.exit_reason = 'SL'
                        snapshot.pnl_percent = pnl_pct
                        snapshot.pnl_usdt = pnl_usdt
                        snapshot.is_winner = pnl_pct > 0
                        
                        autotuner.record_trade_outcome(snapshot)
                        position_manager.remove_position(trade_id)
                        continue
                    
                    # Проверяем выход по TP
                    if pos['side'] == 'BUY' and current_price >= pos['tp_price']:
                        logger.info(f"[CYCLE_{cycle_count}] CLOSE POSITION {trade_id}: Take Profit hit at {current_price}")
                        pnl_pct = (current_price - pos['entry_price']) / pos['entry_price'] * 100
                        pnl_usdt = pnl_pct * pos['position_pct'] * config.getfloat('GENERAL', 'initial_balance') / 100
                        
                        snapshot = position_manager.position_snapshots[trade_id]
                        snapshot.exit_price = current_price
                        snapshot.exit_reason = 'TP'
                        snapshot.pnl_percent = pnl_pct
                        snapshot.pnl_usdt = pnl_usdt
                        snapshot.is_winner = True
                        
                        autotuner.record_trade_outcome(snapshot)
                        position_manager.remove_position(trade_id)
                        continue
                    
                    # Проверяем trailing stop
                    if pos['side'] == 'BUY':
                        atr = analysis.get('5m', {}).get('atr', 0)
                        trail_result = trailing.calculate_trail(
                            entry_price=pos['entry_price'],
                            current_price=current_price,
                            atr=atr,
                            high_since_entry=pos['high_since_entry'],
                            context=context
                        )
                        
                        if trail_result and current_price <= trail_result['trail_price']:
                            logger.info(f"[CYCLE_{cycle_count}] CLOSE POSITION {trade_id}: Trailing Stop at {trail_result['trail_price']}")
                            pnl_pct = (current_price - pos['entry_price']) / pos['entry_price'] * 100
                            pnl_usdt = pnl_pct * pos['position_pct'] * config.getfloat('GENERAL', 'initial_balance') / 100
                            
                            snapshot = position_manager.position_snapshots[trade_id]
                            snapshot.exit_price = current_price
                            snapshot.exit_reason = 'TRAILING'
                            snapshot.pnl_percent = pnl_pct
                            snapshot.pnl_usdt = pnl_usdt
                            snapshot.is_winner = pnl_pct > 0
                            
                            autotuner.record_trade_outcome(snapshot)
                            position_manager.remove_position(trade_id)
            
            # === НОВЫЕ СИГНАЛЫ (только если нет активных позиций) ===
            if position_manager.get_active_count() == 0:
                # Prepare signal data
                signal_data = {
                    'timestamp': cycle_start.isoformat(),
                    'cycle': cycle_count,
                    'confidence': current_confidence,
                    'threshold': threshold,
                    'analysis': analysis,
                    'prices': {
                        'current': current_price
                    },
                    'lineage_summary': {
                        'avg_confidence': score_lineage.confidence if score_lineage else 0,
                        'min_confidence': min(lg.confidence for lg in confidence_result.get('component_lineages', {}).values()) if confidence_result.get('component_lineages') else 0
                    }
                }
                
                # Decision making
                if current_confidence >= threshold:
                    # Calculate position size dynamically
                    position_info = position_sizer.calculate(
                        current_confidence,
                        context,
                        current_price
                    )
                    
                    signal_data['decision'] = 'OPEN'
                    signal_data['position'] = position_info
                    signal_data['weights_used'] = optimized_weights
                    
                    logger.info(f"[CYCLE_{cycle_count}] SIGNAL: OPEN | Confidence: {current_confidence:.3f} >= {threshold:.3f}")
                    logger.info(f"Position: {position_info['position_pct']}% | SL: {position_info['sl_pct']}% | TP R/R: {position_info['rr_ratio']}")
                    logger.info(f"SL Reasoning: ATR({position_info['reasoning']['atr_source']})={position_info['reasoning']['atr_pct']:.2f}% | Regime: {position_info['reasoning']['regime_adjustment']} | Patterns: {position_info['reasoning']['pattern_adjustment']}")
                    logger.info(f"Data Quality Factor: {position_info['reasoning']['data_quality_factor']:.2f} | Details: {position_info['reasoning']['quality_details']}")
                    
                    # Create trade snapshot for Autotuner tracking
                    analyzer_results = {
                        'btc': btc_result,
                        'fractal': fractal_result,
                        'orderbook': orderbook_result,
                        'pattern': pattern_result,
                        'regime': regime_result
                    }
                    trade_snapshot = shadow.create_trade_snapshot(
                        trade_info={
                            'trade_id': f"live_{cycle_count}",
                            'symbol': symbol,
                            'side': 'BUY',
                            'entry_price': current_price,
                            'sl_percent': position_info['sl_pct'],
                            'tp_percent': position_info.get('tp_pct', 2.0),
                            'position_size': position_info['position_pct'],
                            'confidence': current_confidence,
                            'reasoning': position_info['reasoning']
                        },
                        analyzer_results=analyzer_results,
                        weights=optimized_weights
                    )
                    
                    # Сохраняем как TradeContextSnapshot для Autotuner
                    snapshot_obj = TradeContextSnapshot(
                        trade_id=f"live_{cycle_count}",
                        timestamp=datetime.now().timestamp(),
                        symbol=symbol,
                        side='BUY',
                        btc_correlation=analyzer_results['btc'].get('correlation', 0),
                        btc_confidence=analyzer_results['btc'].get('confidence', 0),
                        fractal_score=analyzer_results['fractal'].get('score', 0),
                        orderbook_score=analyzer_results['orderbook'].get('score', 0),
                        pattern_score=analyzer_results['pattern'].get('signal', 0),
                        regime_score=analyzer_results['regime'].get('score', 0),
                        regime_type=analyzer_results['regime'].get('regime', 'UNKNOWN'),
                        weights_used=optimized_weights,
                        entry_price=current_price,
                        sl_percent=position_info['sl_pct'],
                        tp_percent=position_info.get('tp_pct', 2.0),
                        position_size=position_info['position_pct'],
                        final_confidence=current_confidence,
                        exit_price=None,
                        exit_reason=None,
                        pnl_percent=0.0,
                        pnl_usdt=0.0,
                        is_winner=False,
                        max_drawdown_during_trade=0.0,
                        max_profit_during_trade=0.0
                    )
                    
                    # Добавляем позицию в менеджер
                    position_manager.add_position(
                        f"live_{cycle_count}",
                        {
                            'entry_price': current_price,
                            'side': 'BUY',
                            'sl_price': position_info['sl_price'],
                            'tp_price': position_info['tp_price'],
                            'position_pct': position_info['position_pct']
                        },
                        snapshot_obj
                    )
                    
                    # TODO: Execute real trade via Binance API
                    # await binance.place_order(side='BUY', quantity=..., price=current_price)
                    
                else:
                    signal_data['decision'] = 'HOLD'
                    signal_data['reason'] = f'Low confidence: {current_confidence:.2f} < {threshold:.2f}'
                    
                    logger.info(f"[CYCLE_{cycle_count}] HOLD | Confidence: {current_confidence:.3f} < {threshold:.3f}")
                    
                    # Shadow calculation for forbidden trades
                    if config.getboolean('SHADOW', 'save_forbidden_trades'):
                        shadow_result = shadow.analyze_forbidden_trade(signal_data, context_snapshot=context.to_dict() if hasattr(context, 'to_dict') else None)
                        logger.debug(f"Shadow analysis saved for forbidden trade")
                
                # Log signal to database
                db.log_signal(signal_data)
            
            # Run shadow tests
            if config.getboolean('SHADOW', 'enabled'):
                shadow.run_tests(all_data, analysis, current_confidence)
            
            # Periodic Autotuner optimization (every 10 cycles)
            if cycle_count % 10 == 0:
                logger.info("Running Autotuner optimization...")
                new_weights = autotuner.analyze_and_optimize()
                logger.info(f"Autotuner weights updated: {new_weights}")
            
            # Generate report every 5 minutes
            if (datetime.now() - last_report_time).seconds >= 300:
                report = reporter.generate_report()
                logger.info("\\n" + "="*60)
                logger.info("PERIODIC REPORT")
                logger.info("="*60)
                for key, value in report.items():
                    logger.info(f"{key}: {value}")
                logger.info("="*60 + "\\n")
                last_report_time = datetime.now()
            
            # Wait for next cycle
            await asyncio.sleep(30)
            
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
    except Exception as e:
        logger.error(f"Critical error: {e}", exc_info=True)
    finally:
        # Final report
        final_report = reporter.generate_report()
        logger.info("\\n" + "="*60)
        logger.info("FINAL SESSION REPORT")
        logger.info("="*60)
        for key, value in final_report.items():
            logger.info(f"{key}: {value}")
        logger.info("="*60)
        
        db.close()
        await binance.close()
        logger.info("TENBID shutdown complete")


if __name__ == '__main__':
    asyncio.run(main())
