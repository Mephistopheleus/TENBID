"""
Market Regime Analyzer
Определяет текущее состояние рынка: Тренд (бычий/медвежий), Флэт (боковик), Высокая волатильность.
Это критически важно для фильтрации сигналов от других анализаторов.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple
from core.data_lineage import DataLineage, AnalysisContext, DataSource, DataQuality
from datetime import datetime

class MarketRegimeAnalyzer:
    def __init__(self):
        self.name = "MarketRegimeAnalyzer"
        # Пороги могут быть адаптированы автотюнером в будущем
        self.adx_trend_threshold = 25.0
        self.adx_strong_threshold = 40.0
        self.volatility_spike_multiplier = 2.0

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
        Анализирует рынок и определяет режим.
        Возвращает словарь с режимом, уверенностью и метаданными.
        """
        lineage = DataLineage(
            source=DataSource.CALCULATED,
            quality=DataQuality.MEDIUM,
            timestamp=datetime.now(),
            calculation_method="ADX_ATR_regime_detection",
            metadata={
                "input_data": ["candles", "synthetic_timeframes"],
                "parameters": {
                    "adx_period": 14,
                    "trend_threshold": self.adx_trend_threshold
                },
                "description": "Определение рыночного режима через ADX и структуру волатильности"
            }
        )

        try:
            # Используем старший ТФ для определения глобального режима, если есть, иначе базовый
            if context.synthetic_data and '4h' in context.synthetic_data:
                df = context.synthetic_data['4h']
                timeframe_used = '4h'
            elif context.synthetic_data and '1h' in context.synthetic_data:
                df = context.synthetic_data['1h']
                timeframe_used = '1h'
            else:
                df = context.market_data.get(context.symbol) if context.symbol in context.market_data else next(iter(context.market_data.values()), None)
                timeframe_used = context.timeframe

            if df is None or df.empty:
                raise ValueError("Нет данных для анализа режима")

            # Расчет ADX
            adx, plus_di, minus_di = self.calculate_adx(df)
            
            current_adx = adx.iloc[-1]
            current_plus_di = plus_di.iloc[-1]
            current_minus_di = minus_di.iloc[-1]

            # Расчет волатильности (ATR) для определения "Хаоса"
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = ranges.rolling(14).mean()
            current_atr = atr.iloc[-1]
            avg_atr = atr.iloc[-20:-1].mean() if len(atr) > 20 else current_atr
            
            volatility_ratio = current_atr / avg_atr if avg_atr > 0 else 1.0

            # Логика определения режима
            regime = "UNKNOWN"
            confidence = 0.0
            details = {}

            if volatility_ratio > self.volatility_spike_multiplier:
                regime = "HIGH_VOLATILITY" # Хаос, новости, памп/дамп
                confidence = min(1.0, (volatility_ratio - 1) / 2)
                details["reason"] = "Аномальный рост волатильности (ATR)"
            
            elif current_adx < self.adx_trend_threshold:
                regime = "RANGING" # Флэт
                # Уверенность выше, если ADX очень низкий
                confidence = 1.0 - (current_adx / self.adx_trend_threshold)
                details["reason"] = "Слабый тренд (Низкий ADX)"
            
            else:
                # Тренд
                if current_plus_di > current_minus_di:
                    regime = "TREND_UP"
                    di_diff = current_plus_di - current_minus_di
                else:
                    regime = "TREND_DOWN"
                    di_diff = current_minus_di - current_plus_di
                
                # Уверенность растет с ростом ADX и разницы DI
                adx_score = min(1.0, (current_adx - self.adx_trend_threshold) / (self.adx_strong_threshold - self.adx_trend_threshold))
                di_score = min(1.0, di_diff / 20) # Нормализация разницы DI
                confidence = 0.5 * adx_score + 0.5 * di_score
                details["reason"] = f"Сильный {'бычий' if regime == 'TREND_UP' else 'медвежий'} импульс"

            result = {
                "regime": regime,
                "confidence": confidence,
                "metrics": {
                    "adx": float(current_adx),
                    "plus_di": float(current_plus_di),
                    "minus_di": float(current_minus_di),
                    "atr": float(current_atr),
                    "volatility_ratio": float(volatility_ratio)
                },
                "timeframe_used": timeframe_used,
                "details": details,
                "lineage": lineage
            }

            context.add_result(self.name, result, lineage)
            
            return result

        except Exception as e:
            error_result = {"regime": "ERROR", "confidence": 0.0, "error": str(e)}
            context.add_result(self.name, error_result, lineage)
            return error_result
