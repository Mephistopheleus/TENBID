"""
BTC Correlation Analyzer
Анализирует влияние движения Bitcoin на целевую альткоин-пару.
Использует коэффициент корреляции Пирсона с учетом временных лагов.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
from core.data_lineage import AnalysisContext, LineageTracker, DataSource, DataQuality
from datetime import datetime, timedelta

class BTCCorrelationAnalyzer:
    def __init__(self, binance_client):
        self.client = binance_client
        self.name = "BTC_Correlation"
        
    def analyze(self, symbol: str, context: AnalysisContext) -> Dict:
        """
        Анализирует корреляцию пары с BTCUSDT.
        Возвращает коэффициент корреляции, направление влияния и уверенность.
        """
        try:
            # Получаем данные по целевой паре из контекста (чтобы не грузить дважды)
            df_main = context.get_data(DataSource.MARKET_DATA, symbol=symbol)
            if df_main is None or df_main.empty:
                return {"error": "No main data available", "confidence": 0.0}

            # Определяем базовый актив (если это не USDT пара)
            base_asset = symbol.replace('USDT', '').replace('BUSD', '')
            btc_symbol = "BTCUSDT"
            
            # Если это сам BTC, корреляция 1.0
            if base_asset == "BTC":
                lineage = LineageTracker.create_calculated(
                    method="BTC_direct_correlation",
                    dependencies=[context.data_lineage] if context.data_lineage else [],
                    quality=DataQuality.HIGH,
                    metadata={'correlation': 1.0, 'influence': 'DIRECT'}
                )
                context.add_result(self.name, {
                    "correlation": 1.0,
                    "influence": "DIRECT",
                    "confidence": 1.0,
                    "lag_minutes": 0,
                    "btc_trend": self._determine_trend(df_main)
                }, lineage)
                
                return {
                    "correlation": 1.0,
                    "influence": "DIRECT",
                    "confidence": 1.0,
                    "lag_minutes": 0,
                    "btc_trend": self._determine_trend(df_main),
                    "lineage": lineage
                }

            # Загружаем данные BTC за тот же период
            # Берем с запасом по времени для расчетов лагов
            end_time = df_main.index[-1]
            start_time = df_main.index[0] - timedelta(hours=24) 
            
            df_btc = self._fetch_btc_data(btc_symbol, start_time, end_time)
            
            if df_btc is None or df_btc.empty:
                lineage = LineageTracker.create_calculated(
                    method="BTC_correlation_missing_data",
                    dependencies=[context.data_lineage] if context.data_lineage else [],
                    quality=DataQuality.LOW,
                    metadata={'error': 'BTC data unavailable'}
                )
                result = {
                    "correlation": 0.0,
                    "influence": "UNKNOWN",
                    "confidence": 0.0,
                    "error": "BTC data unavailable",
                    "lineage": lineage
                }
                context.add_result(self.name, result, lineage)
                return result

            # Синхронизируем временные метки (resample к общему ТФ)
            timeframe = context.timeframe
            df_sync = self._synchronize_data(df_main, df_btc, timeframe)
            
            if len(df_sync) < 20:
                lineage = LineageTracker.create_calculated(
                    method="BTC_correlation_insufficient_data",
                    dependencies=[context.data_lineage] if context.data_lineage else [],
                    quality=DataQuality.LOW,
                    metadata={'sample_size': len(df_sync)}
                )
                result = {
                    "correlation": 0.0,
                    "influence": "UNKNOWN",
                    "confidence": 0.0,
                    "error": "Insufficient synchronized data",
                    "lineage": lineage
                }
                context.add_result(self.name, result, lineage)
                return result

            # Расчет корреляции доходностей (логарифмических)
            corr_value, lag = self._calculate_rolling_correlation(df_sync, window=24)
            
            # Определение типа влияния
            influence_type = self._classify_influence(corr_value)
            
            # Оценка уверенности (зависит от силы корреляции и объема данных)
            confidence = min(1.0, abs(corr_value) * (len(df_sync) / 100))
            if len(df_sync) < 50:
                confidence *= 0.8  # Штраф за малое количество данных

            # Текущий тренд BTC
            btc_trend = self._determine_trend(df_sync[['close_btc']])

            # Создаем маркировку
            lineage = LineageTracker.create_calculated(
                method="BTC_rolling_correlation_lag_adjusted",
                dependencies=[context.data_lineage] if context.data_lineage else [],
                quality=DataQuality.MEDIUM if len(df_sync) >= 50 else DataQuality.LOW,
                metadata={
                    'correlation': corr_value,
                    'lag_minutes': lag,
                    'sample_size': len(df_sync),
                    'btc_trend': btc_trend
                }
            )

            result = {
                "correlation": round(corr_value, 4),
                "influence": influence_type,
                "confidence": round(confidence, 4),
                "lag_minutes": lag,
                "btc_trend": btc_trend,
                "sample_size": len(df_sync),
                "lineage": lineage
            }

            # Сохраняем в контекст для трассировки
            context.add_result(self.name, result, lineage)
            
            return result

        except Exception as e:
            lineage = LineageTracker.create_calculated(
                method="BTC_correlation_error",
                dependencies=[context.data_lineage] if context.data_lineage else [],
                quality=DataQuality.VERY_LOW,
                metadata={'error': str(e)}
            )
            result = {
                "error": str(e),
                "correlation": 0.0,
                "confidence": 0.0,
                "lineage": lineage
            }
            if hasattr(context, 'add_result'):
                context.add_result(self.name, result, lineage)
            return result

    def _fetch_btc_data(self, symbol: str, start: datetime, end: datetime) -> Optional[pd.DataFrame]:
        """Загружает свечи BTC."""
        try:
            # В реальном проекте здесь вызов клиента с ограничением частоты
            klines = self.client.get_klines(
                symbol=symbol,
                interval='1h', # Используем часовой для долгосрочной корреляции
                start_time=int(start.timestamp() * 1000),
                end_time=int(end.timestamp() * 1000),
                limit=1000
            )
            
            df = pd.DataFrame(klines, columns=[
                'time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base', 'taker_buy_quote', 'ignore'
            ])
            df['time'] = pd.to_datetime(df['time'], unit='ms')
            df.set_index('time', inplace=True)
            df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
            return df[['close']]
        except Exception:
            return None

    def _synchronize_data(self, df_main: pd.DataFrame, df_btc: pd.DataFrame, tf: str) -> pd.DataFrame:
        """Приводит два датафрейма к общему виду."""
        # Ресемплинг к единому таймфрейму (упрощенно берем последний price)
        df_m = df_main[['close']].copy()
        df_b = df_btc.rename(columns={'close': 'close_btc'})
        
        # Объединение по индексу времени
        df_merged = pd.merge_asof(
            df_m.reset_index(), 
            df_b.reset_index(), 
            on='time', 
            direction='nearest',
            tolerance=pd.Timedelta('1h')
        ).set_index('time')
        
        return df_merged.dropna()

    def _calculate_rolling_correlation(self, df: pd.DataFrame, window: int) -> Tuple[float, int]:
        """Считает корреляцию и проверяет лаги."""
        # Лог-доходности
        ret_main = np.log(df['close'] / df['close'].shift(1))
        ret_btc = np.log(df['close_btc'] / df['close_btc'].shift(1))
        
        # Базовая корреляция (без лага)
        corr = ret_main.rolling(window=window).corr(ret_btc).iloc[-1]
        
        # Проверка лагов (опережает ли BTC?)
        best_lag = 0
        best_corr = corr if not np.isnan(corr) else 0.0
        
        # Проверяем лаги 1-4 бара (для 1H это 1-4 часа)
        for lag in range(1, 5):
            shifted_btc = ret_btc.shift(lag)
            c = ret_main.rolling(window=window).corr(shifted_btc).iloc[-1]
            if not np.isnan(c) and abs(c) > abs(best_corr):
                best_corr = c
                best_lag = lag
                
        return best_corr, best_lag

    def _classify_influence(self, corr: float) -> str:
        if corr >= 0.8: return "STRONG_POSITIVE"
        if corr >= 0.5: return "MODERATE_POSITIVE"
        if corr >= 0.2: return "WEAK_POSITIVE"
        if corr >= -0.2: return "NEUTRAL"
        if corr >= -0.5: return "WEAK_NEGATIVE"
        if corr >= -0.8: return "MODERATE_NEGATIVE"
        return "STRONG_NEGATIVE"

    def _determine_trend(self, df: pd.DataFrame) -> str:
        """Простое определение тренда по последним N свечам."""
        if len(df) < 5: return "UNKNOWN"
        last_close = df['close'].iloc[-1]
        prev_close = df['close'].iloc[-5]
        if last_close > prev_close * 1.01: return "BULLISH"
        if last_close < prev_close * 0.99: return "BEARISH"
        return "SIDEWAYS"
