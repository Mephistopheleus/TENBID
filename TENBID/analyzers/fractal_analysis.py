"""
Fractal Analysis Module - Multi-Timeframe Support
Анализ фрактальной структуры рынка (паттерны Вильямса) на разных таймфреймах.
Используется для определения локальных разворотов и подтверждения уровней S/R.
Поддерживает анализ на нескольких таймфреймах одновременно.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from core.data_lineage import DataLineageManager, LineageNode, LineageGraph
from analyzers.multi_tf_context import MultiTFContextAggregator

class FractalAnalyzer:
    def __init__(self, config=None):
        self.name = "Fractal_Analysis"
        self.config = config
        # Таймфреймы для анализа (если переданы в конфиге)
        self.timeframes = ['1h', '15m', '5m']  # Default hierarchy
        if config and config.has_option('MULTITF', 'timeframe_hierarchy'):
            self.timeframes = config.get_list('MULTITF', 'timeframe_hierarchy')
    
    def analyze(self, symbol: str, context: AnalysisContext) -> Dict:
        """
        Выполняет фрактальный анализ на всех доступных таймфреймах.
        Ищет паттерны разворота и кластеры фракталов.
        Возвращает агрегированные результаты с мульти-ТФ контекстом.
        """
        try:
            # Собираем данные со всех доступных таймфреймов
            tf_data = self._collect_all_timeframe_data(context, symbol)
            
            if not tf_data:
                lineage = LineageTracker.create_calculated(
                    method="fractal_analysis_no_data",
                    dependencies=[context.data_lineage] if context.data_lineage else [],
                    quality=DataQuality.VERY_LOW,
                    metadata={'error': 'No data available on any timeframe'}
                )
                return {"error": "No data available", "confidence": 0.5, "lineage": lineage}

            # Выполняем анализ на каждом таймфрейме
            tf_analysis_results = {}
            lineages = []
            
            for tf, (df, lineage) in tf_data.items():
                tf_result = self._analyze_single_timeframe(symbol, tf, df, lineage, context)
                if tf_result and 'error' not in tf_result:
                    tf_analysis_results[tf] = tf_result
                    if tf_result.get('lineage'):
                        lineages.append(tf_result['lineage'])
            
            if not tf_analysis_results:
                lineage = LineageTracker.create_calculated(
                    method="fractal_analysis_failed",
                    dependencies=[context.data_lineage] if context.data_lineage else [],
                    quality=DataQuality.LOW,
                    metadata={'error': 'Analysis failed on all timeframes'}
                )
                return {"error": "Analysis failed", "confidence": 0.5, "lineage": lineage}

            # Агрегируем результаты с разных таймфреймов
            aggregator = MultiTFContextAggregator(self.config) if self.config else MultiTFContextAggregator.__new__(MultiTFContextAggregator)
            if self.config:
                aggregator.__init__(self.config)
            else:
                aggregator.tf_hierarchy = ['1h', '15m', '5m']
                aggregator.tf_weights = {'1h': 0.5, '15m': 0.3, '5m': 0.2}
            
            # Конвертируем результаты в формат для агрегатора
            tf_analysis_for_aggregator = {}
            for tf, result in tf_analysis_results.items():
                # Определяем тренд по последнему фракталу
                trend = self._determine_trend_from_fractals(result)
                tf_analysis_for_aggregator[tf] = {
                    'trend': trend,
                    'trend_strength': result.get('cluster_strength', 0.0),
                    'support': result.get('nearest_support', 0.0),
                    'resistance': result.get('nearest_resistance', 0.0),
                    'volume_score': 0.0,  # Фракталы не используют объем
                    'atr': 0.0,
                    'confidence': result.get('confidence', 0.0)
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
                "signal": self._convert_trend_to_signal(multi_tf_context.dominant_trend),
                "confidence": multi_tf_context.composite_confidence,
                "major_support": multi_tf_context.major_support,
                "major_resistance": multi_tf_context.major_resistance,
                "lineage": multi_tf_context.lineage
            }
            
            context.add_result(self.name, final_result, multi_tf_context.lineage)
            return final_result

        except Exception as e:
            lineage = LineageTracker.create_calculated(
                method="fractal_analysis_error",
                dependencies=[context.data_lineage] if context.data_lineage else [],
                quality=DataQuality.VERY_LOW,
                metadata={'error': str(e)}
            )
            return {
                "error": str(e),
                "confidence": 0.5,
                "lineage": lineage
            }
    
    def _collect_all_timeframe_data(self, context: AnalysisContext, symbol: str) -> Dict[str, Tuple]:
        """
        Собирает данные со всех доступных таймфреймов (базовых + синтетических).
        Returns: dict {timeframe: (df, lineage)}
        """
        tf_data = {}
        
        # Проверяем базовые market data
        base_df = context.get_data(DataSource.MARKET_DATA, symbol=symbol)
        if base_df is not None and not base_df.empty:
            tf_data[context.timeframe] = (base_df, context.data_lineage)
        
        # Проверяем синтетические таймфреймы
        for tf in self.timeframes:
            synthetic_df = context.get_data(DataSource.SYNTHETIC_TF, timeframe=tf)
            if synthetic_df is not None and not synthetic_df.empty:
                synthetic_lineage = LineageTracker.create_calculated(
                    method=f"synthetic_{tf}",
                    dependencies=[context.data_lineage] if context.data_lineage else [],
                    quality=DataQuality.MEDIUM,
                    metadata={'timeframe': tf, 'source': 'synthetic'}
                )
                tf_data[tf] = (synthetic_df, synthetic_lineage)
        
        return tf_data
    
    def _analyze_single_timeframe(self, symbol: str, tf: str, df: pd.DataFrame, 
                                   lineage, context: AnalysisContext) -> Dict:
        """
        Анализирует фракталы на одном таймфрейме.
        """
        if df is None or df.empty:
            return {"error": f"No data for {tf}", "confidence": 0.0}

        # 1. Расчет классических фракталов Вильямса (5 свечей)
        fractals = self._calculate_williams_fractals(df)
        
        if fractals.empty:
            return {
                "status": "NO_FRACTALS",
                "confidence": 0.5,
                "timeframe": tf
            }

        # 2. Поиск кластеров (скоплений фракталов) - сильные уровни
        clusters = self._find_fractal_clusters(fractals, threshold=3)
        
        # 3. Определение текущего состояния
        last_up = fractals[fractals['up_fractal'] == 1].index[-1] if not fractals[fractals['up_fractal'] == 1].empty else None
        last_down = fractals[fractals['down_fractal'] == 1].index[-1] if not fractals[fractals['down_fractal'] == 1].empty else None
        
        current_signal = "NEUTRAL"
        if last_up and last_down:
            if last_up > last_down:
                current_signal = "BEARISH_REVERSAL_PENDING"
            else:
                current_signal = "BULLISH_REVERSAL_PENDING"
        
        # 4. Оценка силы сигнала
        confidence = self._calculate_confidence(fractals, clusters)
        
        # Находим ближайшие уровни поддержки/сопротивления
        nearest_support = self._get_nearest_level(fractals, 'down', df['close'].iloc[-1]) if not fractals.empty else 0.0
        nearest_resistance = self._get_nearest_level(fractals, 'up', df['close'].iloc[-1]) if not fractals.empty else 0.0
        
        # Сила кластеров
        cluster_strength = max([c['strength'] for c in clusters]) if clusters else 0.0

        result_lineage = LineageTracker.create_calculated(
            method="williams_fractals_cluster_analysis",
            dependencies=[lineage] if lineage else [],
            quality=DataQuality.MEDIUM if confidence > 0.5 else DataQuality.LOW,
            metadata={
                'fractals_count': len(fractals),
                'clusters_count': len(clusters),
                'signal': current_signal,
                'timeframe': tf
            }
        )
        
        return {
            "fractals_count": len(fractals),
            "last_up_fractal": {"time": str(last_up), "price": float(fractals.loc[last_up, 'high'])} if last_up else None,
            "last_down_fractal": {"time": str(last_down), "price": float(fractals.loc[last_down, 'low'])} if last_down else None,
            "clusters": clusters,
            "signal": current_signal,
            "confidence": round(confidence, 4),
            "cluster_strength": cluster_strength,
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
            "timeframe": tf,
            "lineage": result_lineage
        }

    def _calculate_williams_fractals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Классический фрактал Вильямса:
        Up: High[2] > High[1] и High[2] > High[3] (середина выше соседей)
        Down: Low[2] < Low[1] и Low[2] < Low[3]
        Требуется 5 свечей для подтверждения (i-2, i-1, i, i+1, i+2)
        """
        if len(df) < 5:
            return pd.DataFrame()
            
        df_f = df.copy()
        
        # Смещения для проверки паттерна из 5 свечей
        # Фрактал подтверждается на закрытии 5-й свечи (индекс i+2 относительно центра i)
        
        # Верхние фракталы
        df_f['up_fractal'] = 0
        mask_up = (
            (df_f['high'].shift(2) > df_f['high'].shift(1)) &
            (df_f['high'].shift(2) > df_f['high'].shift(3)) &
            (df_f['high'].shift(2) > df_f['high'].shift(4)) & # левый хвост
            (df_f['high'].shift(2) > df_f['high'])             # правый хвост (подтверждение)
        )
        df_f.loc[mask_up, 'up_fractal'] = 1
        df_f.loc[mask_up, 'fractal_price'] = df_f['high'].shift(2)

        # Нижние фракталы
        df_f['down_fractal'] = 0
        mask_down = (
            (df_f['low'].shift(2) < df_f['low'].shift(1)) &
            (df_f['low'].shift(2) < df_f['low'].shift(3)) &
            (df_f['low'].shift(2) < df_f['low'].shift(4)) &
            (df_f['low'].shift(2) < df_f['low'])
        )
        df_f.loc[mask_down, 'down_fractal'] = 1
        df_f.loc[mask_down, 'fractal_price'] = df_f['low'].shift(2)
        
        # Оставляем только строки с фракталами
        return df_f[(df_f['up_fractal'] == 1) | (df_f['down_fractal'] == 1)]

    def _determine_trend_from_fractals(self, result: Dict) -> int:
        """
        Определяет тренд (+1/-1/0) по результатам анализа фракталов.
        Returns: 1=bullish, -1=bearish, 0=neutral
        """
        signal = result.get('signal', 'NEUTRAL')
        if signal == 'BULLISH_REVERSAL_PENDING':
            return 1
        elif signal == 'BEARISH_REVERSAL_PENDING':
            return -1
        return 0
    
    def _convert_trend_to_signal(self, dominant_trend: str) -> str:
        """Конвертирует доминирующий тренд в торговый сигнал."""
        if dominant_trend == 'BULLISH':
            return 'LONG'
        elif dominant_trend == 'BEARISH':
            return 'SHORT'
        return 'NEUTRAL'
    
    def _get_nearest_level(self, fractals: pd.DataFrame, fractal_type: str, current_price: float) -> float:
        """Находит ближайший уровень поддержки или сопротивления."""
        if fractals.empty:
            return 0.0
        
        if fractal_type == 'down':
            # Поддержка - ближайшие нижние фракталы ниже текущей цены
            support_fractals = fractals[fractals['down_fractal'] == 1]
            if not support_fractals.empty:
                below = support_fractals[support_fractals['fractal_price'] < current_price]
                if not below.empty:
                    return float(below['fractal_price'].iloc[-1])
        else:
            # Сопротивление - ближайшие верхние фракталы выше текущей цены
            resistance_fractals = fractals[fractals['up_fractal'] == 1]
            if not resistance_fractals.empty:
                above = resistance_fractals[resistance_fractals['fractal_price'] > current_price]
                if not above.empty:
                    return float(above['fractal_price'].iloc[-1])
        
        return 0.0

    def _find_fractal_clusters(self, df_fractals: pd.DataFrame, threshold: int = 3) -> List[Dict]:
        """
        Ищет скопления фракталов в узком ценовом диапазоне.
        Кластер = сильный уровень поддержки/сопротивления.
        """
        if df_fractals.empty:
            return []
            
        clusters = []
        # Группируем по цене с допуском 0.5%
        df_fractals['price_group'] = (df_fractals['fractal_price'] / 0.005).round() * 0.005
        
        grouped = df_fractals.groupby('price_group')
        
        for price, group in grouped:
            if len(group) >= threshold:
                clusters.append({
                    "price_level": float(price),
                    "touch_count": len(group),
                    "type": "RESISTANCE" if group['up_fractal'].sum() > group['down_fractal'].sum() else "SUPPORT",
                    "strength": min(1.0, len(group) / 5.0) # Нормализация силы
                })
                
        return sorted(clusters, key=lambda x: x['strength'], reverse=True)

    def _calculate_confidence(self, df_fractals: pd.DataFrame, clusters: List) -> float:
        """Расчет общей уверенности анализа (без higher_tf)."""
        score = 0.0
        
        # Наличие свежих фракталов (последние 20 свечей)
        if not df_fractals.empty:
            last_time = df_fractals.index[-1]
            recent = df_fractals[df_fractals.index > last_time - pd.Timedelta(minutes=20*15)] # Пример для 15m
            if not recent.empty:
                score += 0.3
                
        # Наличие кластеров
        if len(clusters) > 0:
            score += 0.4 * max(c['strength'] for c in clusters)
        
        # Бонус за количество фракталов (до 0.3)
        if len(df_fractals) >= 10:
            score += 0.3
            
        return min(1.0, score)
