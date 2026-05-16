"""
Orderbook Analysis Module
Анализ стакана цен (Order Book) для оценки давления покупателей/продавцов.
Влияет на уровни S/R, выявляет крупные лимитные ордера (стены).
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from core.data_lineage import AnalysisContext, LineageTracker, DataSource, DataQuality

class OrderbookAnalyzer:
    def __init__(self, binance_client):
        self.client = binance_client
        self.name = "Orderbook_Analysis"
        # Глубина анализа (количество уровней)
        self.depth_levels = 20
        
    def analyze(self, symbol: str, context: AnalysisContext) -> Dict:
        """
        Анализирует текущий стакан цен.
        Возвращает imbalance, стены ликвидности и скорректированные уровни S/R.
        """
        try:
            # Получаем срез стакана
            ob_data = self._fetch_orderbook(symbol, limit=self.depth_levels)
            
            if not ob_data:
                lineage = LineageTracker.create_calculated(
                    method="orderbook_analysis_missing_data",
                    dependencies=[context.data_lineage] if context.data_lineage else [],
                    quality=DataQuality.VERY_LOW,
                    metadata={'error': 'Orderbook data unavailable'}
                )
                # Fallback: нейтральная оценка вместо 0.0 чтобы не убивать confidence
                return {
                    "error": "Orderbook data unavailable",
                    "confidence": 0.5,
                    "lineage": lineage
                }
                
            bids = pd.DataFrame(ob_data['bids'], columns=['price', 'qty']).astype(float)
            asks = pd.DataFrame(ob_data['asks'], columns=['price', 'qty']).astype(float)
            
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
            lineage = LineageTracker.create_calculated(
                method="orderbook_imbalance_wall_detection",
                dependencies=[context.data_lineage] if context.data_lineage else [],
                quality=DataQuality.HIGH, # Стакан - свежие данные
                metadata={
                    'volume_imbalance': imbalance,
                    'walls_detected': len(bid_walls) + len(ask_walls),
                    'near_price_imbalance': near_imbalance
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
                "lineage": lineage
            }

            context.add_result(self.name, result, lineage)
            return result

        except Exception as e:
            lineage = LineageTracker.create_calculated(
                method="orderbook_analysis_error",
                dependencies=[context.data_lineage] if context.data_lineage else [],
                quality=DataQuality.VERY_LOW,
                metadata={'error': str(e)}
            )
            # Fallback: нейтральная оценка вместо 0.0 чтобы не убивать confidence
            return {
                "error": str(e),
                "confidence": 0.5,
                "lineage": lineage
            }

    def _fetch_orderbook(self, symbol: str, limit: int = 20) -> Optional[Dict]:
        """Загружает стакан с биржи."""
        try:
            # Binance API: depth endpoint
            # limit: 5, 10, 20, 50, 100, 500, 1000, 5000
            data = self.client.get_order_book(symbol=symbol, limit=limit)
            return data
        except Exception:
            return None

    def _find_walls(self, df: pd.DataFrame, threshold_factor: float = 3.0) -> List[Dict]:
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
