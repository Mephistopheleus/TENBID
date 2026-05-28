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
