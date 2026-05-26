"""
Market Regime Analyzer
Определяет текущее состояние рынка: Тренд (бычий/медвежий), Флэт (боковик), Высокая волатильность.
Это критически важно для фильтрации сигналов от других анализаторов.
Поддерживает мульти-ТФ анализ.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple, Optional
from core.data_lineage import DataLineageManager, LineageNode, LineageGraph
from datetime import datetime
from .multi_tf_context import MultiTFContextAggregator

class MarketRegimeAnalyzer:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.name = "MarketRegimeAnalyzer"
        # Пороги могут быть адаптированы автотюнером в будущем
        self.adx_trend_threshold = 25.0
        self.adx_strong_threshold = 40.0
        self.volatility_spike_multiplier = 2.0
        self.aggregator = MultiTFContextAggregator(config)

    def calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Расчет индекса среднего направления (ADX) для силы тренда."""
        high = df['high']
        low = df['low']
        close = df['close']

        plus_dm = high.diff()
        minus_dm = low.diff()

        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm > 0] = 0
        
        # Условие: +DM > -DM иначе 0, и наоборот
        condition1 = plus_dm > minus_dm
        condition2 = plus_dm < minus_dm
        
        plus_dm = np.where(condition1, plus_dm, 0)
        minus_dm = np.where(condition2, minus_dm, 0)

        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.rolling(window=period).mean()
        plus_di = 100 * (pd.Series(plus_dm).rolling(window=period).mean() / atr)
        minus_di = 100 * (pd.Series(minus_dm).rolling(window=period).mean() / atr)

        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        return adx, plus_di, minus_di

    def analyze(self, context: AnalysisContext) -> Dict[str, Any]:
        """
        Анализирует рынок и определяет режим с поддержкой мульти-ТФ.
        Возвращает словарь с режимом, уверенностью и метаданными.
        """
        lineage = DataLineage(
            source=DataSource.CALCULATED,
            quality=DataQuality.MEDIUM,
            timestamp=datetime.now(),
            calculation_method="ADX_ATR_regime_detection_multi_tf",
            metadata={
                "input_data": ["candles", "synthetic_timeframes"],
                "parameters": {
                    "adx_period": 14,
                    "trend_threshold": self.adx_trend_threshold
                },
                "description": "Определение рыночного режима через ADX и структуру волатильности на всех ТФ"
            }
        )

        try:
            # Собираем данные со всех доступных ТФ
            tf_data = self._collect_all_timeframe_data(context)
            
            if not tf_data:
                raise ValueError("Нет данных для анализа режима")
            
            # Анализируем каждый ТФ отдельно
            per_timeframe_results = {}
            for timeframe, df in tf_data.items():
                result = self._analyze_single_timeframe(df, timeframe)
                per_timeframe_results[timeframe] = result
            
            if not per_timeframe_results:
                raise ValueError("Нет валидных данных ни на одном ТФ")
            
            # Агрегируем результаты
            aggregated = self.aggregator.aggregate_regime_signals(per_timeframe_results)
            
            result = {
                "regime": aggregated["regime"],
                "confidence": aggregated["confidence"],
                "metrics": aggregated["metrics"],
                "per_timeframe_results": per_timeframe_results,
                "multi_tf_context": aggregated.get("multi_tf_context"),
                "lineage": lineage
            }
            
            context.add_result(self.name, result, lineage)
            
            return result

        except Exception as e:
            error_result = {"regime": "ERROR", "confidence": 0.5, "error": str(e)}
            context.add_result(self.name, error_result, lineage)
            return error_result
    
    def _collect_all_timeframe_data(self, context) -> Dict[str, Any]:
        """Собирает данные со всех доступных ТФ (базовых + синтетических)."""
        tf_data = {}
        
        # Базовые данные
        if context.market_data:
            for symbol, df in context.market_data.items():
                tf_data[context.timeframe] = df
                break
        
        # Синтетические ТФ
        if context.synthetic_data:
            for tf, data_tuple in context.synthetic_data.items():
                if isinstance(data_tuple, tuple) and len(data_tuple) > 0:
                    tf_data[tf] = data_tuple[0]
                else:
                    tf_data[tf] = data_tuple
        
        return tf_data
    
    def _analyze_single_timeframe(self, df, timeframe: str) -> Dict[str, Any]:
        """Анализ режима на одном ТФ."""
        if df is None or df.empty or len(df) < 20:
            return {"regime": "NO_DATA", "confidence": 0.0, "timeframe": timeframe}
        
        # Расчет ADX
        adx, plus_di, minus_di = self.calculate_adx(df)
        
        current_adx = adx.iloc[-1] if len(adx) > 0 else 0
        current_plus_di = plus_di.iloc[-1] if len(plus_di) > 0 else 0
        current_minus_di = minus_di.iloc[-1] if len(minus_di) > 0 else 0

        # Расчет волатильности (ATR)
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = ranges.rolling(14).mean()
        current_atr = atr.iloc[-1] if len(atr) > 0 else 0
        avg_atr = atr.iloc[-20:-1].mean() if len(atr) > 20 else current_atr
        
        volatility_ratio = current_atr / avg_atr if avg_atr > 0 else 1.0

        # Логика определения режима
        regime = "UNKNOWN"
        confidence = 0.0
        details = {}

        if volatility_ratio > self.volatility_spike_multiplier:
            regime = "HIGH_VOLATILITY"
            confidence = min(1.0, (volatility_ratio - 1) / 2)
            details["reason"] = "Аномальный рост волатильности (ATR)"
        
        elif current_adx < self.adx_trend_threshold:
            regime = "RANGING"
            confidence = 1.0 - (current_adx / self.adx_trend_threshold)
            details["reason"] = "Слабый тренд (Низкий ADX)"
        
        else:
            if current_plus_di > current_minus_di:
                regime = "TREND_UP"
                di_diff = current_plus_di - current_minus_di
            else:
                regime = "TREND_DOWN"
                di_diff = current_minus_di - current_plus_di
            
            adx_score = min(1.0, (current_adx - self.adx_trend_threshold) / (self.adx_strong_threshold - self.adx_trend_threshold))
            di_score = min(1.0, di_diff / 20)
            confidence = 0.5 * adx_score + 0.5 * di_score
            details["reason"] = f"Сильный {'бычий' if regime == 'TREND_UP' else 'медвежий'} импульс"

        return {
            "regime": regime,
            "confidence": confidence,
            "timeframe": timeframe,
            "metrics": {
                "adx": float(current_adx),
                "plus_di": float(current_plus_di),
                "minus_di": float(current_minus_di),
                "atr": float(current_atr),
                "volatility_ratio": float(volatility_ratio)
            },
            "details": details
        }
