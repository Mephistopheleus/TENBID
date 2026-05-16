"""
Fractal Analysis Module
Анализ фрактальной структуры рынка (паттерны Вильямса) на разных таймфреймах.
Используется для определения локальных разворотов и подтверждения уровней S/R.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from core.data_lineage import AnalysisContext, LineageTracker, DataSource, DataQuality

class FractalAnalyzer:
    def __init__(self):
        self.name = "Fractal_Analysis"
        
    def analyze(self, symbol: str, context: AnalysisContext) -> Dict:
        """
        Выполняет фрактальный анализ на доступных таймфреймах.
        Ищет паттерны разворота и кластеры фракталов.
        """
        try:
            df = context.get_data(DataSource.MARKET_DATA, symbol=symbol)
            if df is None or df.empty:
                lineage = LineageTracker.create_calculated(
                    method="fractal_analysis_missing_data",
                    dependencies=[context.data_lineage] if context.data_lineage else [],
                    quality=DataQuality.VERY_LOW,
                    metadata={'error': 'No data available'}
                )
                # Fallback: нейтральная оценка вместо 0.0 чтобы не убивать confidence
                return {"error": "No data available", "confidence": 0.5, "lineage": lineage}

            # 1. Расчет классических фракталов Вильямса (5 свечей)
            fractals = self._calculate_williams_fractals(df)
            
            if fractals.empty:
                lineage = LineageTracker.create_calculated(
                    method="fractal_analysis_no_patterns",
                    dependencies=[context.data_lineage] if context.data_lineage else [],
                    quality=DataQuality.LOW,
                    metadata={'status': 'NO_FRACTALS'}
                )
                # Fallback: нейтральная оценка вместо 0.0 чтобы не убивать confidence
                return {
                    "status": "NO_FRACTALS",
                    "confidence": 0.5,
                    "lineage": lineage
                }

            # 2. Анализ старших ТФ (если доступны в контексте)
            higher_tf_fractals = self._analyze_higher_timeframe(context, symbol)
            
            # 3. Поиск кластеров (скоплений фракталов) - сильные уровни
            clusters = self._find_fractal_clusters(fractals, threshold=3)
            
            # 4. Определение текущего состояния
            last_up = fractals[fractals['up_fractal'] == 1].index[-1] if not fractals[fractals['up_fractal'] == 1].empty else None
            last_down = fractals[fractals['down_fractal'] == 1].index[-1] if not fractals[fractals['down_fractal'] == 1].empty else None
            
            current_signal = "NEUTRAL"
            if last_up and last_down:
                if last_up > last_down:
                    current_signal = "BEARISH_REVERSAL_PENDING"
                else:
                    current_signal = "BULLISH_REVERSAL_PENDING"
            
            # 5. Оценка силы сигнала
            confidence = self._calculate_confidence(fractals, clusters, higher_tf_fractals)
            
            # Создаем маркировку
            lineage = LineageTracker.create_calculated(
                method="williams_fractals_cluster_analysis",
                dependencies=[context.data_lineage] if context.data_lineage else [],
                quality=DataQuality.MEDIUM if confidence > 0.5 else DataQuality.LOW,
                metadata={
                    'fractals_count': len(fractals),
                    'clusters_count': len(clusters),
                    'signal': current_signal,
                    'higher_tf_confirmation': higher_tf_fractals.get("confirmed", False)
                }
            )
            
            result = {
                "fractals_count": len(fractals),
                "last_up_fractal": {"time": str(last_up), "price": float(fractals.loc[last_up, 'high'])} if last_up else None,
                "last_down_fractal": {"time": str(last_down), "price": float(fractals.loc[last_down, 'low'])} if last_down else None,
                "clusters": clusters,
                "higher_tf_confirmation": higher_tf_fractals.get("confirmed", False),
                "signal": current_signal,
                "confidence": round(confidence, 4),
                "lineage": lineage
            }

            context.add_result(self.name, result, lineage)
            return result

        except Exception as e:
            lineage = LineageTracker.create_calculated(
                method="fractal_analysis_error",
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

    def _analyze_higher_timeframe(self, context: AnalysisContext, symbol: str) -> Dict:
        """
        Проверяет наличие фрактальных сигналов на старшем ТФ.
        """
        # Пытаемся получить синтетический старший ТФ (например, 4h если основной 15m)
        # В текущей реализации просто эмулируем проверку
        # В полной версии: context.get_data(DataSource.SYNTHETIC_TF, timeframe='4h')
        
        # Эмуляция: если на текущем ТФ много фракталов, считаем что старший тоже активен
        # Это заглушка до полной интеграции с SyntheticTimeframes
        return {"confirmed": False, "reason": "Higher TF data not linked yet"}

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

    def _calculate_confidence(self, df_fractals: pd.DataFrame, clusters: List, higher_tf: Dict) -> float:
        """Расчет общей уверенности анализа."""
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
            
        # Подтверждение старшим ТФ
        if higher_tf.get("confirmed"):
            score += 0.3
            
        return min(1.0, score)
