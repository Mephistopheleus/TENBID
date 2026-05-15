"""
TENBID - Advanced Scalping Trading System for Binance
Complete modular architecture with shadow calculations and adaptive confidence
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
            
            # Analyze market (теперь анализ включает маркировку)
            analysis = market_analyzer.analyze(all_data)
            
            # Создаем контекст анализа с полной маркировкой
            symbol = config.get('GENERAL', 'symbol')
            base_tf = '5m'  # Базовый таймфрейм
            
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
            
            # Calculate confidence с полной маркировкой
            confidence_result = confidence_sys.calculate(analysis, all_data, btc_result, fractal_result, orderbook_result, pattern_result, regime_result)
            current_confidence = confidence_result['total_confidence']
            score_lineage = confidence_result.get('score_lineage')
            
            # Get optimized weights from Autotuner (dynamic, not static)
            optimized_weights = autotuner.get_recommendation({})
            
            # Get adaptive threshold
            threshold = confidence_sys.get_adaptive_threshold(analysis)
            
            # Prepare signal data with full markers
            signal_data = {
                'timestamp': cycle_start.isoformat(),
                'cycle': cycle_count,
                'confidence': current_confidence,
                'threshold': threshold,
                'analysis': analysis,
                'prices': {
                    'current': all_data['5m'][0].iloc[-1]['close'] if len(all_data['5m']) > 0 else 0
                },
                'lineage_summary': {
                    'avg_confidence': score_lineage.confidence if score_lineage else 0,
                    'min_confidence': min(lg.confidence for lg in confidence_result.get('component_lineages', {}).values()) if confidence_result.get('component_lineages') else 0
                }
            }
            
            # Decision making
            if current_confidence >= threshold:
                # Calculate position size dynamically (using optimized weights)
                position_info = position_sizer.calculate(
                    current_confidence,
                    analysis,
                    all_data['5m'].iloc[-1]['close'] if len(all_data['5m']) > 0 else 0,
                    optimized_weights  # Pass Autotuner weights
                )
                
                signal_data['decision'] = 'OPEN'
                signal_data['position'] = position_info
                signal_data['weights_used'] = optimized_weights  # Store for snapshot
                
                logger.info(f"[CYCLE_{cycle_count}] SIGNAL: OPEN | Confidence: {current_confidence:.3f} >= {threshold:.3f}")
                logger.info(f"Position: {position_info['position_pct']}% | SL: {position_info['sl_pct']}% | TP R/R: {position_info['rr_ratio']}")
                
                # Create initial trade snapshot for Autotuner tracking
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
                        'side': 'BUY',  # Simplified, should come from signal direction
                        'entry_price': all_data['5m'][0].iloc[-1]['close'] if len(all_data['5m']) > 0 else 0,
                        'sl_percent': position_info['sl_pct'],
                        'tp_percent': position_info.get('tp_pct', 2.0),
                        'position_size': position_info['position_size'],
                        'confidence': current_confidence
                    },
                    analyzer_results=analyzer_results,
                    weights=optimized_weights
                )
                # Store snapshot in context for later update when trade closes
                context.active_trade_snapshot = trade_snapshot
                
                # Execute trade (placeholder - will integrate with real execution)
                # await binance.execute_trade(...)
                
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
            
            # Periodic Autotuner optimization (every 10 cycles or when trade closes)
            if cycle_count % 10 == 0:
                logger.info("Running Autotuner optimization...")
                new_weights = autotuner.analyze_and_optimize()
                logger.info(f"Autotuner weights updated: {new_weights}")
            
            # Generate report every 5 minutes
            if (datetime.now() - last_report_time).seconds >= 300:
                report = reporter.generate_report()
                logger.info("\n" + "="*60)
                logger.info("PERIODIC REPORT")
                logger.info("="*60)
                for key, value in report.items():
                    logger.info(f"{key}: {value}")
                logger.info("="*60 + "\n")
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
        logger.info("\n" + "="*60)
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
