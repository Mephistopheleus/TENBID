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
from confidence.confidence_system import ConfidenceSystem
from trading.position_sizer import PositionSizer
from trading.smart_trailing import SmartTrailing
from shadow.shadow_calculator import ShadowCalculator
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
    binance = BinanceConnector(config)
    data_mgr = DataManager(config, binance)
    synth_tf = SyntheticTimeframes(config)
    market_analyzer = MarketAnalyzer(config)
    confidence_sys = ConfidenceSystem(config)
    position_sizer = PositionSizer(config)
    trailing = SmartTrailing(config)
    shadow = ShadowCalculator(config, db)
    reporter = Reporter(db, config)
    
    # Connect to Binance
    await binance.connect()
    logger.info("Connected to Binance API")
    
    # Warmup - load historical data
    logger.info(f"Warming up with {config.getint('DATA', 'warmup_candles')} candles...")
    candles = await data_mgr.load_warmup_data()
    logger.info(f"Loaded {len(candles)} base candles")
    
    # Build synthetic timeframes
    synth_data = synth_tf.build_all(candles)
    logger.info(f"Built {len(synth_data)} synthetic timeframes")
    
    # Main trading loop
    cycle_count = 0
    last_report_time = datetime.now()
    
    try:
        while True:
            cycle_start = datetime.now()
            cycle_count += 1
            
            # Fetch new data
            new_candles = await data_mgr.fetch_latest()
            all_data = synth_tf.build_all(new_candles)
            
            # Analyze market
            analysis = market_analyzer.analyze(all_data)
            
            # Calculate confidence
            confidence_result = confidence_sys.calculate(analysis, all_data)
            current_confidence = confidence_result['total_confidence']
            
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
                    'current': all_data['5m'].iloc[-1]['close'] if len(all_data['5m']) > 0 else 0
                }
            }
            
            # Decision making
            if current_confidence >= threshold:
                # Calculate position size dynamically
                position_info = position_sizer.calculate(
                    current_confidence,
                    analysis,
                    all_data['5m'].iloc[-1]['close'] if len(all_data['5m']) > 0 else 0
                )
                
                signal_data['decision'] = 'OPEN'
                signal_data['position'] = position_info
                
                logger.info(f"[CYCLE_{cycle_count}] SIGNAL: OPEN | Confidence: {current_confidence:.3f} >= {threshold:.3f}")
                logger.info(f"Position: {position_info['position_pct']}% | SL: {position_info['sl_pct']}% | TP R/R: {position_info['rr_ratio']}")
                
                # Execute trade (placeholder - will integrate with real execution)
                # await binance.execute_trade(...)
                
            else:
                signal_data['decision'] = 'HOLD'
                signal_data['reason'] = f'Low confidence: {current_confidence:.2f} < {threshold:.2f}'
                
                logger.info(f"[CYCLE_{cycle_count}] HOLD | Confidence: {current_confidence:.3f} < {threshold:.3f}")
                
                # Shadow calculation for forbidden trades
                if config.getboolean('SHADOW', 'save_forbidden_trades'):
                    shadow_result = shadow.analyze_forbidden_trade(signal_data)
                    logger.debug(f"Shadow analysis saved for forbidden trade")
            
            # Log signal to database
            db.log_signal(signal_data)
            
            # Run shadow tests
            if config.getboolean('SHADOW', 'enabled'):
                shadow.run_tests(all_data, analysis, current_confidence)
            
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
