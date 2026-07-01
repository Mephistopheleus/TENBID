"""
TENBID v2.0 - Advanced Scalping System
Full Integration with DataLineage Manager
"""
import asyncio
import logging
import time
from typing import Dict, List, Any
from binance import AsyncClient
from core.data_lineage import DataLineageManager
from analyzers.market_analyzer import MarketAnalyzer
from analyzers.volume_profile import VolumeProfileAnalyzer
from analyzers.pattern_analyzer import PatternAnalyzer
from analyzers.support_resistance_analyzer import SupportResistanceAnalyzer
from analyzers.orderbook_analyzer import OrderbookAnalyzer
from analyzers.correlation_analyzer import CorrelationAnalyzer
from analyzers.fractal_analyzer import FractalAnalyzer
from confidence.confidence_system import ConfidenceSystem
from core.trade_calculator import TradeCalculator
from trading.adaptive_trailing import AdaptiveTrailing
from shadow.shadow_calculator import ShadowCalculator
from shadow.shadow_lab import ShadowLab
from core.autotuner import Autotuner, init_autotuner_db, TradeContextSnapshot
from core.probability_matrix import ProbabilityMatrix, ForecastInput, MarketScenario
from reports.reporter import Reporter

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TENBIDCore:
    def __init__(self):
        self.client = None
        self.lineage_manager = DataLineageManager()
        
        # Инициализация анализаторов с внедрением зависимостей
        self.market_analyzer = MarketAnalyzer(lineage_manager=self.lineage_manager)
        self.volume_analyzer = VolumeProfileAnalyzer(lineage_manager=self.lineage_manager)
        self.pattern_analyzer = PatternAnalyzer(lineage_manager=self.lineage_manager)
        self.sr_analyzer = SupportResistanceAnalyzer(lineage_manager=self.lineage_manager)
        self.orderbook_analyzer = OrderbookAnalyzer(lineage_manager=self.lineage_manager)
        self.correlation_analyzer = CorrelationAnalyzer(lineage_manager=self.lineage_manager)
        self.fractal_analyzer = FractalAnalyzer(lineage_manager=self.lineage_manager)
        
        # Система уверенности
        self.confidence_system = ConfidenceSystem(lineage_manager=self.lineage_manager)
        
        self.symbol = "DOGEUSDT"
        self.timeframe = "5m"
        self.running = False

    async def start(self):
        """Запуск ядра системы"""
        logger.info("🚀 Запуск TENBID v2.0 Core...")
        
        # Подключение к Binance Testnet
        try:
            self.client = await AsyncClient.create(testnet=True)
            logger.info("✅ Подключено к Binance Testnet")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Binance: {e}")
            return

def collect_forecasts_from_analyzers(analysis, fractal_result, pattern_result, 
                                     btc_result, orderbook_result, regime_result):
    """
    Собирает все прогнозы от анализаторов.
    
    Returns:
        List[Dict]: Список прогнозов в формате для матрицы
    """
    all_forecasts = []
    
    # 1. Прогнозы от market_analyzer
    if analysis and isinstance(analysis, dict):
        for tf, tf_data in analysis.items():
            if isinstance(tf_data, dict) and 'forecasts' in tf_data:
                for forecast in tf_data['forecasts']:
                    all_forecasts.append({
                        'analyzer': 'market_analyzer',
                        'timeframe': forecast.get('timeframe', tf),
                        'forecast': forecast
                    })
    
    # 2. Прогнозы от fractal_analyzer
    if fractal_result and isinstance(fractal_result, dict):
        if 'per_timeframe' in fractal_result:
            for tf, tf_data in fractal_result['per_timeframe'].items():
                if 'forecasts' in tf_data:
                    for forecast in tf_data['forecasts']:
                        all_forecasts.append({
                            'analyzer': 'fractal_analyzer',
                            'timeframe': forecast.get('timeframe', tf),
                            'forecast': forecast
                        })
        elif 'forecasts' in fractal_result:
            for forecast in fractal_result['forecasts']:
                all_forecasts.append({
                    'analyzer': 'fractal_analyzer',
                    'timeframe': forecast.get('timeframe', '5m'),
                    'forecast': forecast
                })
    
    # 3. Прогнозы от pattern_analyzer
    if pattern_result and isinstance(pattern_result, dict):
        if 'per_timeframe' in pattern_result:
            for tf, tf_data in pattern_result['per_timeframe'].items():
                if 'forecasts' in tf_data:
                    for forecast in tf_data['forecasts']:
                        all_forecasts.append({
                            'analyzer': 'pattern_analyzer',
                            'timeframe': forecast.get('timeframe', tf),
                            'forecast': forecast
                        })
        elif 'forecasts' in pattern_result:
            for forecast in pattern_result['forecasts']:
                all_forecasts.append({
                    'analyzer': 'pattern_analyzer',
                    'timeframe': forecast.get('timeframe', '5m'),
                    'forecast': forecast
                })
    
    return all_forecasts


def apply_granular_trust(forecasts, autotuner, regime_type='UNKNOWN'):
    """
    Применяет гранулярное доверие к прогнозам.
    
    Пока используем упрощённую версию - в будущем autotuner будет
    возвращать доверие для каждого (анализатор + ТФ + метрика + режим).
    
    Args:
        forecasts: Список прогнозов
        autotuner: Экземпляр Autotuner
        regime_type: Текущий режим рынка
    
    Returns:
        List[ForecastInput]: Прогнозы с весами доверия
    """
    weighted_forecasts = []
    
    # Получаем базовые веса от автотюнера
    base_weights = autotuner.get_recommendation({})
    
    for item in forecasts:
        analyzer_name = item['analyzer']
        forecast = item['forecast']
        
        # Определяем базовый вес доверия для анализатора
        # В будущем это будет гранулярное доверие (анализатор + ТФ + метрика + режим)
        if analyzer_name == 'market_analyzer':
            trust_weight = base_weights.get('market_analyzer', 1.0)
        elif analyzer_name == 'fractal_analyzer':
            trust_weight = base_weights.get('fractal', 1.0)
        elif analyzer_name == 'pattern_analyzer':
            trust_weight = base_weights.get('pattern', 1.0)
        else:
            trust_weight = 1.0
        
        # Создаём ForecastInput
        try:
            forecast_input = ForecastInput(
                timeframe=forecast.get('timeframe', '5m'),
                horizon_minutes=forecast.get('horizon_minutes', 15),
                scenario=forecast.get('scenario', 'flat'),
                price_target=forecast.get('price_target', 0.0),
                price_range=forecast.get('price_range', {'min': 0.0, 'max': 0.0}),
                confidence=forecast.get('confidence', 0.5),
                strength=forecast.get('strength', 0.5),
                factors=forecast.get('factors', []),
                analyzer_name=analyzer_name,
                trust_weight=trust_weight
            )
            weighted_forecasts.append(forecast_input)
        except Exception as e:
            logging.getLogger('TENBID').warning(f"Failed to create ForecastInput: {e}")
            continue
    
    return weighted_forecasts


def update_probability_matrix(matrix, forecasts, current_price, volatility):
    """
    Обновляет матрицу вероятностей прогнозами.
    
    Args:
        matrix: Экземпляр ProbabilityMatrix
        forecasts: Список ForecastInput
        current_price: Текущая цена
        volatility: Волатильность (ATR)
    """
    logger = logging.getLogger('TENBID')
    
    # Инициализируем сетку матрицы
    matrix.initialize(current_price, volatility)
    
    # Добавляем все прогнозы
    for forecast in forecasts:
        matrix.add_forecast(forecast)
    
    # Применяем Gaussian blur
    if matrix.forecasts_added > 0:
        matrix.apply_blur()
        logger.debug(f"Matrix updated: {matrix.forecasts_added} forecasts added, blur applied")
    else:
        logger.warning("No forecasts added to matrix")


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
    shadow = ShadowCalculator(config, db, binance_connector=binance)
    autotuner = Autotuner()  # Initialize Autotuner
    
    # Initialize Probability Matrix with autotuner parameters
    matrix_params = autotuner.get_matrix_params()
    probability_matrix = ProbabilityMatrix(autotuner_params=matrix_params)
    logger.info(f"📊 Probability Matrix initialized: {matrix_params}")

    # Initialize TradeCalculator with autotuner parameters
    calculator_params = autotuner.get_trade_calculator_params()
    trade_calculator = TradeCalculator(config, autotuner)
    logger.info(f"🧮 TradeCalculator initialized: {calculator_params}")

    # Initialize AdaptiveTrailing with autotuner parameters
    trailing_params = autotuner.get_trailing_params()
    adaptive_trailing = AdaptiveTrailing(config, autotuner)
    logger.info(f"📈 AdaptiveTrailing initialized: {trailing_params}")
    
    shadow_lab = ShadowLab(db.db_path)  # Initialize Shadow Lab
    reporter = Reporter(db, config)
    position_manager = PositionManager()  # Менеджер позиций
    
    # Запуск Shadow Lab в фоновом режиме
    lab_task = asyncio.create_task(shadow_lab.start(interval=120))  # Проверка каждые 2 минуты
    logger.info("🔬 Shadow Lab запущена в фоновом режиме")
    
    # Connect to Binance
    await binance.connect()
    logger.info("Connected to Binance API")
    
    # Update trading costs for Shadow Calculator
    await shadow.update_trading_costs(config.get('GENERAL', 'symbol'))
    
    # Warmup - load historical data
    logger.info(f"Warming up with {config.getint('DATA', 'warmup_candles')} candles...")
    all_data = await data_mgr.load_warmup_data()
    base_tf = config.get('DATA', 'base_timeframe')
    base_candles = all_data[base_tf][0]
    base_lineage = all_data[base_tf][1]
    logger.info(f"Loaded {len(base_candles)} base candles with lineage: {base_lineage.source.value}")
    
    # Build synthetic timeframes
    synth_data = synth_tf.build_all(base_candles, base_lineage)
    # Merge with base data
    all_data.update(synth_data)
    logger.info(f"Built {len(synth_data)} synthetic timeframes with lineage tracking")
    
    # Main trading loop
    cycle_count = 0
    last_report_time = datetime.now()
    
    try:
        while True:
            cycle_start = datetime.now()
            cycle_count += 1
            
            # Fetch new data
            all_data = await data_mgr.fetch_latest()
            base_tf = config.get('DATA', 'base_timeframe')
            base_candles = all_data[base_tf][0]
            base_lineage = all_data[base_tf][1]
            synth_data = synth_tf.build_all(base_candles, base_lineage)
            all_data.update(synth_data)
            
            # Analyze market
            analysis = market_analyzer.analyze(all_data)
            
            # Создаем контекст анализа
            symbol = config.get('GENERAL', 'symbol')
            
            context = AnalysisContext(
                symbol=symbol,
                timeframe=base_tf,
                base_lineage=base_lineage
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
            
            # === ИНТЕГРАЦИЯ МАТРИЦЫ ПРОГНОЗОВ ===
            # 1. Собираем все прогнозы от анализаторов
            all_forecasts = collect_forecasts_from_analyzers(
                analysis, fractal_result, pattern_result,
                btc_result, orderbook_result, regime_result
            )
            
            # 2. Применяем гранулярное доверие от автотюнера
            regime_type = regime_result.get('regime', 'UNKNOWN') if regime_result else 'UNKNOWN'
            weighted_forecasts = apply_granular_trust(all_forecasts, autotuner, regime_type)
            
            # 3. Обновляем матрицу вероятностей
            current_price = all_data['5m'][0].iloc[-1]['close'] if len(all_data['5m'][0]) > 0 else 0
            atr = analysis.get('5m', {}).get('atr', current_price * 0.01) if analysis else current_price * 0.01
            
            update_probability_matrix(probability_matrix, weighted_forecasts, current_price, atr)
            
            # 4. Получаем зоны максимальной вероятности
            probability_zones = probability_matrix.find_max_probability_zones()
            
            # Логируем статистику матрицы
            matrix_stats = probability_matrix.get_statistics()
            logger.debug(f"Matrix stats: {matrix_stats['forecasts_added']} forecasts, "
                        f"max_prob={matrix_stats['max_probability']:.3f}, "
                        f"zones_found={len(probability_zones)}")
            
            if probability_zones:
                top_zone = probability_zones[0]
                logger.info(f"🎯 Top probability zone: {top_zone.scenario.value} @ "
                           f"{top_zone.time_minutes}min, price={top_zone.price_center:.6f}, "
                           f"prob={top_zone.probability:.3f}")
            
            # === КОНЕЦ ИНТЕГРАЦИИ МАТРИЦЫ ===
            
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
            
            # Получаем текущую цену и данные свечи для реалистичной симуляции
            current_price = all_data['5m'][0].iloc[-1]['close'] if len(all_data['5m']) > 0 else 0
            
            # Extract candle data for realistic simulation (high/low of current candle)
            candle_data = None
            if len(all_data['5m']) > 0:
                latest_candle = all_data['5m'][0].iloc[-1]
                candle_data = {
                    'high': latest_candle['high'],
                    'low': latest_candle['low'],
                    'open': latest_candle['open'],
                    'close': latest_candle['close']
                }
            
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
                    
                    # Проверяем adaptive trailing stop
                    if pos['side'] == 'BUY':
                        atr = analysis.get('5m', {}).get('atr', 0)
                        volatility = atr / current_price if current_price > 0 else 0.01

                        # Используем AdaptiveTrailing
                        new_sl = adaptive_trailing.update_trailing_stop(
                            entry_price=pos['entry_price'],
                            current_price=current_price,
                            current_sl=pos['sl_price'],
                            atr=atr,
                            volatility=volatility
                        )
                        
                        # Обновляем SL если изменился
                        if new_sl != pos['sl_price']:
                            pos['sl_price'] = new_sl
                            logger.info(f"[CYCLE_{cycle_count}] Updated trailing SL for {trade_id}: {new_sl:.6f}")

                        # Проверяем выход по trailing stop
                        if current_price <= pos['sl_price']:
                            logger.info(f"[CYCLE_{cycle_count}] CLOSE POSITION {trade_id}: Trailing Stop at {pos['sl_price']}")
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

                # Decision making using TradeCalculator
                regime_type = regime_result.get('regime', 'UNKNOWN')

                # Используем TradeCalculator для принятия решения
                volatility = analysis.get('5m', {}).get('atr', 0) / current_price if current_price > 0 else 0.01
                trade_decision = trade_calculator.calculate_trade(
                    matrix=probability_matrix,
                    current_price=current_price,
                    market_context={
                        'volatility': volatility,
                        'regime_type': regime_type,
                        'atr': analysis.get('5m', {}).get('atr', 0)
                    }
                )

                if trade_decision['decision'] == 'OPEN':
                    signal_data['decision'] = 'OPEN'
                    signal_data['trade_calculation'] = trade_decision
                    signal_data['weights_used'] = optimized_weights
                    
                    logger.info(f"[CYCLE_{cycle_count}] 🎯 SIGNAL: OPEN | Probability: {trade_decision['best_zone']['probability']:.3f}")
                    logger.info(f"📊 Zone: {trade_decision['best_zone']['scenario']} @ {trade_decision['best_zone']['time_minutes']:.1f}min, Price: {trade_decision['best_zone']['price']:.6f}")
                    logger.info(f"💰 Entry: {trade_decision['entry_price']:.6f} | SL: {trade_decision['sl_price']:.6f} ({trade_decision['sl_percent']:.2f}%)")
                    logger.info(f"📈 Expected Profit: {trade_decision['expected_profit_pct']:.2f}% | Net: {trade_decision['net_profit_pct']:.2f}%")
                    logger.info(f"⚖️ R/R: {trade_decision['risk_reward_ratio']:.2f} | Costs: {trade_decision['total_costs_pct']:.3f}%")
                    logger.info(f"🎲 Reasoning: {trade_decision['reasoning']}")
                    
                    # Create trade snapshot for Autotuner tracking
                    analyzer_results = {
                        'btc': btc_result,
                        'fractal': fractal_result,
                        'orderbook': orderbook_result,
                        'pattern': pattern_result,
                        'regime': regime_result
                    }
                    
                    # Сохраняем как TradeContextSnapshot для Autotuner
                    snapshot_obj = TradeContextSnapshot(
                        trade_id=f"live_{cycle_count}",
                        timestamp=datetime.now().timestamp(),
                        symbol=symbol,
                        side='BUY',
                        btc_correlation=analyzer_results['btc'].get('correlation', 0),
                        btc_confidence=analyzer_results['btc'].get('confidence', 0),
                        fractal_score=analyzer_results['fractal'].get('confidence', 0),
                        orderbook_score=analyzer_results['orderbook'].get('confidence', 0),
                        pattern_score=analyzer_results['pattern'].get('signal', 0),
                        regime_score=analyzer_results['regime'].get('confidence', 0),
                        regime_type=regime_type,
                        weights_used=optimized_weights,
                        entry_price=trade_decision['entry_price'],
                        sl_percent=trade_decision['sl_percent'],
                        tp_percent=trade_decision['expected_profit_pct'],
                        position_size=config.getfloat('RISK', 'max_position_pct'),  # From config for now
                        final_confidence=trade_decision['best_zone']['probability'],
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
                            'entry_price': trade_decision['entry_price'],
                            'side': 'BUY',
                            'sl_price': trade_decision['sl_price'],
                            'tp_price': trade_decision['entry_price'] * (1 + trade_decision['expected_profit_pct'] / 100),
                            'position_pct': config.getfloat('RISK', 'max_position_pct')
                        },
                        snapshot_obj
                    )
                    
                    # Execute real trade via Binance API (if not in SHADOW mode)
                    if config.get('GENERAL', 'mode') != 'SHADOW_ONLY':
                        try:
                            # Calculate quantity based on position size and balance
                            balance = config.getfloat('GENERAL', 'initial_balance')
                            position_pct = config.getfloat('RISK', 'max_position_pct')
                            usdt_amount = balance * position_pct / 100
                            quantity = usdt_amount / trade_decision['entry_price']
                            
                            # Place MARKET order for immediate execution
                            order_result = await binance.place_market_order(side='BUY', quantity=quantity)
                            logger.info(f"ORDER EXECUTED: {order_result.get('orderId')} | Status: {order_result.get('status')}")
                            
                            # Store order ID for tracking
                            position_manager.active_positions[f"live_{cycle_count}"]["order_id"] = order_result.get('orderId')
                        except Exception as e:
                            logger.error(f"Failed to execute order: {e}")
                            # Remove position if order failed
                            position_manager.remove_position(f"live_{cycle_count}")
                    
                else:
                    # HOLD decision from TradeCalculator
                    signal_data['decision'] = 'HOLD'
                    signal_data['reason'] = trade_decision.get('reasoning', 'Matrix analysis suggests HOLD')
                    
                    logger.info(f"[CYCLE_{cycle_count}] 🛑 HOLD | Reason: {signal_data['reason']}")
                    
                    # Shadow calculation for forbidden trades - FULL CYCLE
                    if config.getboolean('SHADOW', 'save_forbidden_trades'):
                        # 1. Analyze what would happen (existing)
                        shadow_result = shadow.analyze_forbidden_trade(signal_data, context_snapshot=context.to_dict() if hasattr(context, 'to_dict') else None)
                        
                        # 2. Create complete snapshot for Autotuner (NEW)
                        analyzer_results = {
                            'btc': btc_result,
                            'fractal': fractal_result,
                            'orderbook': orderbook_result,
                            'pattern': pattern_result,
                            'regime': regime_result
                        }
                        forbidden_snapshot = shadow.create_forbidden_snapshot(
                            signal_data=signal_data,
                            analyzer_results=analyzer_results,
                            weights=autotuner.current_weights,
                            context_snapshot=context.to_dict() if hasattr(context, 'to_dict') else None
                        )
                        
                        # 3. Register for delayed outcome checking (NEW)
                        shadow.register_forbidden_trade(forbidden_snapshot)
                        
                        # 4. Send weak factors to Shadow Lab (NEW)
                        weak_factors = shadow.get_weak_factors_for_lab()
                        if weak_factors:
                            logger.debug(f"Sent {len(weak_factors)} weak factor observations to Shadow Lab")
                        
                        logger.info(f"Forbidden trade tracked: {forbidden_snapshot['trade_id']}")
        self.running = True
        await self.trading_cycle()

    async def get_market_data(self) -> Dict[str, Any]:
        """Получение данных рынка"""
        # Свечи
        klines = await self.client.get_klines(symbol=self.symbol, interval=self.timeframe, limit=100)
        candles = [
            {
                'time': k[0], 'open': float(k[1]), 'high': float(k[2]), 
                'low': float(k[3]), 'close': float(k[4]), 'volume': float(k[5])
            }
            for k in klines
        ]
        
        # Стакан
        order_book = await self.client.get_order_book(symbol=self.symbol, limit=20)
        bids = [[float(p), float(q)] for p, q in order_book['bids']]
        asks = [[float(p), float(q)] for p, q in order_book['asks']]
        
        return {'candles': candles, 'bids': bids, 'asks': asks, 'current_price': float(candles[-1]['close'])}

    async def trading_cycle(self):
        """Основной цикл торговли"""
        cycle_count = 0
        
        while self.running and cycle_count < 1: # Ровно один цикл для теста
            try:
                cycle_count += 1
                logger.info(f"\n--- ЦИКЛ АНАЛИЗА #{cycle_count} ---")
                
                # 1. Получение данных
                data = await self.get_market_data()
                candles = data['candles']
                
                # 2. Создание снапшота в Graph Lineage
                snapshot_id = self.lineage_manager.create_snapshot_node(
                    symbol=self.symbol,
                    timeframe=self.timeframe,
                    market_state={'price': data['current_price'], 'volume_24h': 0} # Упрощено
                )
                logger.info(f"📸 Создан снапшот рынка: ID={snapshot_id}")

                # 3. Запуск анализаторов
                results = {}
                
                logger.info("🔍 Запуск анализаторов...")
                
                # Market Analyzer
                results['market'] = self.market_analyzer.analyze(
                    snapshot_id=snapshot_id, candles=candles, symbol=self.symbol, tf=self.timeframe
                )
                
                # Volume Profile
                results['volume'] = self.volume_analyzer.analyze_candles(
                    snapshot_id=snapshot_id, candles=candles, symbol=self.symbol, tf=self.timeframe
                )
                
                # Patterns
                results['patterns'] = self.pattern_analyzer.scan(
                    snapshot_id=snapshot_id, candles=candles, symbol=self.symbol, tf=self.timeframe
                )
                
                # Support/Resistance
                results['sr'] = self.sr_analyzer.find_levels(
                    snapshot_id=snapshot_id, candles=candles, symbol=self.symbol, tf=self.timeframe
                )
                
                # Orderbook
                results['orderbook'] = self.orderbook_analyzer.analyze_depth(
                    snapshot_id=snapshot_id, bids=data['bids'], asks=data['asks'], 
                    symbol=self.symbol, current_price=data['current_price']
                )
                
                # Correlation (эмуляция данных для примера, в реальности нужны данные BTC)
                # Для теста передаем те же свечи как "корреляцию с самим собой"
                closes = [c['close'] for c in candles]
                results['correlation'] = self.correlation_analyzer.calculate_correlation(
                    snapshot_id=snapshot_id, target_series=closes, reference_series=closes,
                    target_symbol=self.symbol, reference_symbol="BTC"
                )
                
                # Fractals
                results['fractals'] = self.fractal_analyzer.analyze(
                    snapshot_id=snapshot_id, candles=candles, symbol=self.symbol, tf=self.timeframe
                )

                # Логирование результатов анализаторов
                for name, res in results.items():
                    status = res.get('status', 'unknown')
                    node_id = res.get('node_id', 'None')
                    logger.info(f"   [{name.upper()}] Status: {status}, Node: {node_id}")

                # 4. Расчет уверенности
                logger.info("🧠 Расчет уверенности (Confidence System)...")
                
                # Извлекаем скоры из результатов (заглушка логики маппинга)
                # В реальной системе нужно аккуратно доставать данные из словарей
                trend_score = results['market'].get('trend_direction', 0.0)
                volume_score = results['volume'].get('confidence', 0.5)
                pattern_score = results['patterns'].get('score', 0.0)
                sr_score = results['sr'].get('confidence', 0.5)
                orderbook_score = results['orderbook'].get('pressure', 0.0)
                fractal_score = 0.5 if results['fractals'].get('signal') != 'NEUTRAL' else 0.0
                
                confidence_result = self.confidence_system.calculate(
                    snapshot_id=snapshot_id,
                    trend_score=trend_score,
                    volume_score=volume_score,
                    pattern_score=pattern_score,
                    support_resistance_score=sr_score, # Имя аргумента может отличаться, проверить сигнатуру
                    orderbook_score=orderbook_score,
                    fractal_score=fractal_score,
                    context_profile_id=f"{self.symbol}_{self.timeframe}"
                )
                
                logger.info(f"✅ Уверенность: {confidence_result['confidence']}")
                logger.info(f"✅ Рекомендация: {confidence_result['recommendation']}")
                logger.info(f"✅ Matrix Node ID: {confidence_result['matrix_node_id']}")
                
                # 5. Финальный отчет по графу
                logger.info("\n🌐 СОЗДАННЫЙ ГРАФ ДАННЫХ:")
                logger.info(f"   Root Snapshot: {snapshot_id}")
                logger.info(f"   Decision Node: {confidence_result['matrix_node_id']}")
                logger.info("   Анализаторы создали узлы: " + ", ".join(str(r.get('node_id')) for r in results.values() if r.get('node_id')))
                
                logger.info("\n--- ЦИКЛ ЗАВЕРШЕН ---\n")
                
                # Прерываем после одного цикла для теста
                self.running = False

            except Exception as e:
                logger.error(f"❌ Критическая ошибка в цикле: {e}", exc_info=True)
                self.running = False
            
            finally:
                if self.client:
                    await self.client.close_connection()

async def main():
    core = TENBIDCore()
    await core.start()

if __name__ == "__main__":
    asyncio.run(main())
