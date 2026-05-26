"""
Orderbook Analysis Module - Multi-Timeframe Support
Анализ стакана цен (Order Book) для оценки давления покупателей/продавцов.
Влияет на уровни S/R, выявляет крупные лимитные ордера (стены).
Поддерживает анализ на нескольких таймфреймах одновременно.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from core.data_lineage import DataLineageManager, LineageNode, LineageGraph
from analyzers.multi_tf_context import MultiTFContextAggregator, TFAnalysis

class OrderbookAnalyzer:
    def __init__(self, binance_client, config=None):
        self.client = binance_client
        self.name = "Orderbook_Analysis"
        self.config = config
        # Глубина анализа (количество уровней)
        self.depth_levels = 20
        # Таймфреймы для анализа (если переданы в конфиге)
        self.timeframes = ['1h', '15m', '5m']  # Default hierarchy
        if config and config.has_option('MULTITF', 'timeframe_hierarchy'):
            self.timeframes = config.get_list('MULTITF', 'timeframe_hierarchy')
        
    def analyze(self, symbol: str, context: AnalysisContext) -> Dict:
        """
        Анализирует стакан цен на всех доступных таймфреймах.
        Возвращает агрегированные результаты с мульти-ТФ контекстом.
        """
        try:
            # Собираем данные со всех доступных таймфреймов
            tf_data = self._collect_all_timeframe_data(context, symbol)
            
            if not tf_data:
                lineage = LineageTracker.create_calculated(
                    method="orderbook_analysis_no_data",
                    dependencies=[context.data_lineage] if context.data_lineage else [],
                    quality=DataQuality.VERY_LOW,
                    metadata={'error': 'No data available on any timeframe'}
                )
                result = {
                    "error": "No data available on any timeframe",
                    "confidence": 0.0,
                    "lineage": lineage
                }
                context.add_result(self.name, result, lineage)
                return result
            
            # Выполняем анализ на каждом таймфрейме
            tf_analysis_results = {}
            lineages = []
            
            for tf, (df_main, ob_snapshot, lineage) in tf_data.items():
                tf_result = self._analyze_single_timeframe(
                    symbol, tf, df_main, ob_snapshot, lineage, context
                )
                if tf_result and 'error' not in tf_result:
                    tf_analysis_results[tf] = tf_result
                    if tf_result.get('lineage'):
                        lineages.append(tf_result['lineage'])
            
            if not tf_analysis_results:
                lineage = LineageTracker.create_calculated(
                    method="orderbook_analysis_failed",
                    dependencies=[context.data_lineage] if context.data_lineage else [],
                    quality=DataQuality.LOW,
                    metadata={'error': 'Analysis failed on all timeframes'}
                )
                result = {
                    "error": "Analysis failed on all timeframes",
                    "confidence": 0.0,
                    "lineage": lineage
                }
                context.add_result(self.name, result, lineage)
                return result
            
            # Агрегируем результаты с разных таймфреймов
            aggregator = MultiTFContextAggregator(self.config) if self.config else MultiTFContextAggregator.__new__(MultiTFContextAggregator)
            if self.config:
                aggregator.__init__(self.config)
            else:
                # Fallback без конфига
                aggregator.tf_hierarchy = ['1h', '15m', '5m']
                aggregator.tf_weights = {'1h': 0.5, '15m': 0.3, '5m': 0.2}
            
            # Конвертируем результаты в формат для агрегатора
            tf_analysis_for_aggregator = {}
            for tf, result in tf_analysis_results.items():
                # Определяем тренд на основе imbalance
                imbalance = result.get('volume_imbalance', 0)
                trend = 1 if imbalance > 0.2 else (-1 if imbalance < -0.2 else 0)
                
                # Рассчитываем силу стен
                wall_strength = len(result.get('bid_walls', [])) + len(result.get('ask_walls', []))
                
                tf_analysis_for_aggregator[tf] = {
                    'trend': trend,
                    'trend_strength': abs(imbalance),
                    'support': min([w['price'] for w in result.get('bid_walls', [])], default=0),
                    'resistance': max([w['price'] for w in result.get('ask_walls', [])], default=0),
                    'volume_score': result.get('near_price_imbalance', 0),
                    'atr': 0,  # Orderbook не предоставляет ATR
                    'confidence': result.get('confidence', 0),
                    'wall_count': wall_strength
                }
            
            multi_tf_context = aggregator.aggregate(tf_analysis_for_aggregator, symbol)
            
            # Формируем итоговый результат
            final_result = {
                "timeframes_analyzed": list(tf_analysis_results.keys()),
                "per_timeframe_results": tf_analysis_results,
                "multi_tf_context": {
                    "dominant_trend": multi_tf_context.dominant_trend,
                    "trend_alignment": multi_tf_context.trend_alignment,
                    "composite_confidence": multi_tf_context.composite_confidence,
                    "trend_conflicts": multi_tf_context.trend_conflicts
                },
                "aggregate_imbalance": multi_tf_context.trend_alignment,
                "dominant_signal": self._classify_signal(multi_tf_context.dominant_trend),
                "confidence": multi_tf_context.composite_confidence,
                "lineage": multi_tf_context.lineage
            }
            
            context.add_result(self.name, final_result, multi_tf_context.lineage)
            return final_result

        except Exception as e:
            lineage = LineageTracker.create_calculated(
                method="orderbook_analysis_error",
                dependencies=[context.data_lineage] if context.data_lineage else [],
                quality=DataQuality.VERY_LOW,
                metadata={'error': str(e)}
            )
            result = {
                "error": str(e),
                "confidence": 0.5,
                "lineage": lineage
            }
            if hasattr(context, 'add_result'):
                context.add_result(self.name, result, lineage)
            return result
    
    def _collect_all_timeframe_data(self, context: AnalysisContext, symbol: str) -> Dict[str, Tuple]:
        """
        Собирает данные со всех доступных таймфреймов (базовых + синтетических).
        Для orderbook используем только текущий snapshot, но привязываем к разным ТФ контекстам.
        Returns: dict {timeframe: (df_main, ob_snapshot, lineage)}
        """
        tf_data = {}
        
        # Получаем актуальный snapshot стакана (он один для всех ТФ)
        ob_snapshot = self._fetch_orderbook(symbol, limit=self.depth_levels)
        
        # Проверяем базовые market data
        base_df = context.get_data(DataSource.MARKET_DATA, symbol=symbol)
        if base_df is not None and not base_df.empty:
            tf_data[context.timeframe] = (base_df, ob_snapshot, context.data_lineage)
        
        # Проверяем синтетические таймфреймы
        for tf in self.timeframes:
            synthetic_df = context.get_data(DataSource.SYNTHETIC_TF, timeframe=tf)
            if synthetic_df is not None and not synthetic_df.empty:
                # Для синтетических данных используем упрощенную маркировку
                synthetic_lineage = LineageTracker.create_calculated(
                    method=f"synthetic_{tf}",
                    dependencies=[context.data_lineage] if context.data_lineage else [],
                    quality=DataQuality.MEDIUM,
                    metadata={'timeframe': tf, 'source': 'synthetic'}
                )
                # Используем тот же snapshot стакана, но в контексте другого ТФ
                tf_data[tf] = (synthetic_df, ob_snapshot, synthetic_lineage)
        
        return tf_data
    
    def _analyze_single_timeframe(self, symbol: str, tf: str, df_main: pd.DataFrame, 
                                   ob_snapshot: Optional[Dict], lineage, 
                                   context: AnalysisContext) -> Dict:
        """
        Анализирует стакан на одном таймфрейме.
        """
        if df_main is None or df_main.empty:
            return {"error": f"No data for {tf}", "confidence": 0.0}
        
        if not ob_snapshot:
            return {"error": f"Orderbook data unavailable for {tf}", "confidence": 0.0}
        
        try:
            bids = pd.DataFrame(ob_snapshot['bids'], columns=['price', 'qty']).astype(float)
            asks = pd.DataFrame(ob_snapshot['asks'], columns=['price', 'qty']).astype(float)
            
            current_price = float(bids['price'].iloc[-1])
            
            # 1. Расчет Volume Imbalance
            total_bid_vol = bids['qty'].sum()
            total_ask_vol = asks['qty'].sum()
            imbalance = (total_bid_vol - total_ask_vol) / (total_bid_vol + total_ask_vol)
            
            # 2. Поиск "Стен"
            bid_walls = self._find_walls(bids, threshold_factor=3.0)
            ask_walls = self._find_walls(asks, threshold_factor=3.0)
            
            # 3. Оценка плотности ликвидности near price
            near_bids = bids[bids['price'] > current_price * 0.99]['qty'].sum()
            near_asks = asks[asks['price'] < current_price * 1.01]['qty'].sum()
            near_imbalance = (near_bids - near_asks) / (near_bids + near_asks + 1e-9)
            
            # 4. Коррекция уровней S/R на основе стакана
            sr_adjustments = []
            for wall in ask_walls:
                sr_adjustments.append({
                    "type": "RESISTANCE_BOOST",
                    "price": wall['price'],
                    "strength": wall['relative_strength'],
                    "reason": "Large Ask Wall detected"
                })
            for wall in bid_walls:
                sr_adjustments.append({
                    "type": "SUPPORT_BOOST",
                    "price": wall['price'],
                    "strength": wall['relative_strength'],
                    "reason": "Large Bid Wall detected"
                })
            
            # 5. Итоговая оценка уверенности
            confidence = min(1.0, abs(imbalance) * 2)
            if len(bid_walls) + len(ask_walls) > 0:
                confidence = min(1.0, confidence + 0.2)
            
            # Создаем маркировку
            result_lineage = LineageTracker.create_calculated(
                method=f"orderbook_imbalance_wall_detection_{tf}",
                dependencies=[lineage] if lineage else [],
                quality=DataQuality.HIGH,
                metadata={
                    'volume_imbalance': imbalance,
                    'walls_detected': len(bid_walls) + len(ask_walls),
                    'near_price_imbalance': near_imbalance,
                    'timeframe': tf
                }
            )
            
            result = {
                "current_price": current_price,
                "volume_imbalance": round(imbalance, 4),
                "near_price_imbalance": round(near_imbalance, 4),
                "bid_walls": bid_walls,
                "ask_walls": ask_walls,
                "sr_adjustments": sr_adjustments,
                "total_bid_volume": round(total_bid_vol, 2),
                "total_ask_volume": round(total_ask_vol, 2),
                "confidence": round(confidence, 4),
                "timeframe": tf,
                "lineage": result_lineage
            }
            
            return result
            
        except Exception as e:
            return {
                "error": str(e),
                "confidence": 0.0,
                "timeframe": tf
            }
    
    def _classify_signal(self, trend: int) -> str:
        """Классифицирует сигнал на основе тренда."""
        if trend > 0:
            return "BULLISH"
        elif trend < 0:
            return "BEARISH"
        else:
            return "NEUTRAL"
    
    def _fetch_orderbook(self, symbol: str, limit: int = 20):
        """Загружает стакан с биржи."""
        try:
            # Binance API: depth endpoint
            # limit: 5, 10, 20, 50, 100, 500, 1000, 5000
            # Используем тот же event loop, в котором работает main цикл
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Создаем задачу и ждем её выполнения
            future = asyncio.run_coroutine_threadsafe(
                self.client.get_order_book(symbol=symbol, limit=limit),
                loop
            )
            data = future.result(timeout=5)  # Таймаут 5 секунд
            return data
        except Exception:
            return None

    def _find_walls(self, df: pd.DataFrame, threshold_factor: float = 3.0):
        """Ищет ордера, превышающие средний объем в N раз."""
        if df.empty:
            return []
            
        avg_qty = df['qty'].mean()
        threshold = avg_qty * threshold_factor
        
        walls = []
        for _, row in df.iterrows():
            if row['qty'] >= threshold:
                walls.append({
                    "price": float(row['price']),
                    "volume": float(row['qty']),
                    "relative_strength": round(row['qty'] / avg_qty, 2)
                })
        
        # Сортируем по силе
        return sorted(walls, key=lambda x: x['relative_strength'], reverse=True)[:3] # Топ 3 стены
