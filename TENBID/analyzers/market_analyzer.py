"""Market Analyzer - analyzes price action, trends, support/resistance"""
import logging
from typing import Dict, List, Any, Optional
from core.data_lineage import DataLineageManager

logger = logging.getLogger(__name__)


class MarketAnalyzer:
    """
    Основной анализатор рынка.
    Рассчитывает тренд, волатильность и объем для различных таймфреймов.
    Интегрирован с DataLineageManager v2.0.
    """

    def __init__(self, lineage_manager: DataLineageManager):
        if lineage_manager is None:
            raise ValueError("lineage_manager cannot be None")
        self.lineage_manager = lineage_manager
        self.logger = logging.getLogger(__name__)

    # --- Математические утилиты (Сохранены полностью) ---

    def _calculate_sma(self, data: List[float], period: int) -> Optional[float]:
        if len(data) < period:
            return None
        return sum(data[-period:]) / period

    def _calculate_ema(self, data: List[float], period: int) -> Optional[float]:
        if len(data) < period:
            return None
        multiplier = 2 / (period + 1)
        ema = sum(data[:period]) / period
        for price in data[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        return ema

    def _calculate_atr(self, highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
        if len(highs) < period + 1:
            return None
        
        tr_values = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            tr_values.append(tr)
        
        # Простое среднее для первых значений или экспоненциальное
        atr = sum(tr_values[:period]) / period
        for tr in tr_values[period:]:
            atr = (atr * (period - 1) + tr) / period
        
        return atr

    def _calculate_volume_ratio(self, current_volume: float, avg_volume: float) -> float:
        if avg_volume == 0:
            return 1.0
        return current_volume / avg_volume

    def _determine_trend_direction(self, sma_short: float, sma_long: float, price: float) -> str:
        if sma_short > sma_long and price > sma_short:
            return "BULLISH"
        elif sma_short < sma_long and price < sma_short:
            return "BEARISH"
        else:
            return "NEUTRAL"

    def _calculate_momentum(self, closes: List[float], period: int = 10) -> Optional[float]:
        if len(closes) < period + 1:
            return None
        return closes[-1] - closes[-period-1]

    # --- Основной метод анализа ---

    def analyze(self, market_data: Dict[str, Any], snapshot_id: str, context_profile_id: str) -> Dict[str, Any]:
        """
        Выполняет комплексный анализ рынка по всем таймфреймам.
        Создает узлы линейности для каждого компонента.
        
        :param market_data: Словарь вида {'5m': {...}, '1h': {...}, ...}
        :param snapshot_id: ID корневого снимка рынка.
        :param context_profile_id: Идентификатор контекста (напр., 'BTCUSDT').
        :return: Словарь с результатами анализа и ID созданных узлов.
        """
        results = {
            'context_profile_id': context_profile_id,
            'snapshot_id': snapshot_id,
            'timeframes': {},
            'lineage_nodes': [],  # Список ID всех созданных узлов
            'summary': {}
        }

        timeframes = market_data.keys()
        
        for tf in timeframes:
            tf_data = market_data[tf]
            closes = tf_data.get('closes', [])
            highs = tf_data.get('highs', [])
            lows = tf_data.get('lows', [])
            volumes = tf_data.get('volumes', [])
            
            if not closes or len(closes) < 20:
                self.logger.warning(f"Insufficient data for timeframe {tf}")
                continue

            try:
                # 1. Расчет индикаторов
                sma_short = self._calculate_sma(closes, 9)
                sma_long = self._calculate_sma(closes, 21)
                ema_fast = self._calculate_ema(closes, 12)
                ema_slow = self._calculate_ema(closes, 26)
                atr = self._calculate_atr(highs, lows, closes)
                
                current_price = closes[-1]
                current_volume = volumes[-1] if volumes else 0
                avg_volume = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else current_volume
                
                vol_ratio = self._calculate_volume_ratio(current_volume, avg_volume)
                trend_dir = self._determine_trend_direction(sma_short or 0, sma_long or 0, current_price)
                momentum = self._calculate_momentum(closes)

                # Нормализация уверенности для тренда (0..1)
                trend_confidence = 0.5
                if trend_dir == "BULLISH":
                    trend_confidence = min(1.0, (sma_short - sma_long) / (sma_long * 0.01) + 0.5) if sma_long else 0.5
                elif trend_dir == "BEARISH":
                    trend_confidence = min(1.0, (sma_long - sma_short) / (sma_short * 0.01) + 0.5) if sma_short else 0.5
                
                # 2. Создание узлов линейности (Lineage Nodes)
                
                # Узел Тренда
                trend_vector = {
                    'direction': trend_dir,
                    'sma_short': sma_short,
                    'sma_long': sma_long,
                    'momentum': momentum,
                    'price': current_price
                }
                try:
                    trend_node_id = self.lineage_manager.create_analysis_node(
                        parent_snapshot_id=snapshot_id,
                        analyzer_name=f"trend_{tf}",
                        result_vector=trend_vector,
                        confidence=trend_confidence,
                        additional_meta={'timeframe': tf, 'type': 'trend'}
                    )
                    results['lineage_nodes'].append(trend_node_id)
                except Exception as e:
                    self.logger.error(f"Failed to create trend node for {tf}: {e}")
                    trend_node_id = None

                # Узел Волатильности (ATR)
                vol_confidence = 0.8 if atr else 0.1
                volatility_vector = {
                    'atr': atr,
                    'atr_percent': (atr / current_price * 100) if atr and current_price else 0
                }
                try:
                    vol_node_id = self.lineage_manager.create_analysis_node(
                        parent_snapshot_id=snapshot_id,
                        analyzer_name=f"volatility_{tf}",
                        result_vector=volatility_vector,
                        confidence=vol_confidence,
                        additional_meta={'timeframe': tf, 'type': 'volatility'}
                    )
                    results['lineage_nodes'].append(vol_node_id)
                except Exception as e:
                    self.logger.error(f"Failed to create volatility node for {tf}: {e}")
                    vol_node_id = None

                # Узел Объема
                volume_confidence = min(1.0, vol_ratio / 2.0) # Пример эвристики
                volume_vector = {
                    'current_volume': current_volume,
                    'avg_volume': avg_volume,
                    'ratio': vol_ratio
                }
                try:
                    vol_node_id = self.lineage_manager.create_analysis_node(
                        parent_snapshot_id=snapshot_id,
                        analyzer_name=f"volume_{tf}",
                        result_vector=volume_vector,
                        confidence=volume_confidence,
                        additional_meta={'timeframe': tf, 'type': 'volume'}
                    )
                    results['lineage_nodes'].append(vol_node_id)
                except Exception as e:
                    self.logger.error(f"Failed to create volume node for {tf}: {e}")

                # Сохранение результатов по TF
                results['timeframes'][tf] = {
                    'trend': trend_dir,
                    'trend_confidence': trend_confidence,
                    'atr': atr,
                    'volume_ratio': vol_ratio,
                    'momentum': momentum,
                    'nodes_count': len([n for n in results['lineage_nodes'] if tf in str(n)]) # Грубая оценка
                }

            except Exception as e:
                self.logger.error(f"Critical error analyzing timeframe {tf}: {e}")
                continue

        # Итоговое резюме
        bullish_count = sum(1 for tf in results['timeframes'].values() if tf['trend'] == 'BULLISH')
        bearish_count = sum(1 for tf in results['timeframes'].values() if tf['trend'] == 'BEARISH')
        
        if bullish_count > bearish_count:
            results['summary']['overall_trend'] = 'BULLISH'
        elif bearish_count > bullish_count:
            results['summary']['overall_trend'] = 'BEARISH'
        else:
            results['summary']['overall_trend'] = 'NEUTRAL'
            
        results['summary']['timeframes_analyzed'] = len(results['timeframes'])
        results['summary']['total_nodes_created'] = len(results['lineage_nodes'])

        return results

