"""
BTC Correlation Analyzer - Multi-Timeframe Support
Анализирует влияние движения Bitcoin на целевую альткоин-пару.
Использует коэффициент корреляции Пирсона с учетом временных лагов.
Поддерживает анализ на нескольких таймфреймах одновременно.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple, List
from core.data_lineage import AnalysisContext, LineageTracker, DataSource, DataQuality
from datetime import datetime, timedelta
from analyzers.multi_tf_context import MultiTFContextAggregator, TFAnalysis

class BTCCorrelationAnalyzer:
    def __init__(self, binance_client, config=None):
        self.client = binance_client
        self.name = "BTC_Correlation"
        self.config = config
        # Таймфреймы для анализа (если переданы в конфиге)
        self.timeframes = ['1h', '15m', '5m']  # Default hierarchy
        if config and config.has_option('MULTITF', 'timeframe_hierarchy'):
            self.timeframes = config.get_list('MULTITF', 'timeframe_hierarchy')
    
    def analyze(self, symbol: str, context: AnalysisContext) -> Dict:
        """
        Анализирует корреляцию пары с BTCUSDT на всех доступных таймфреймах.
        Возвращает агрегированные результаты с мульти-ТФ контекстом.
        """
        try:
            # Собираем данные со всех доступных таймфреймов
            tf_data = self._collect_all_timeframe_data(context, symbol)
            
            if not tf_data:
                lineage = LineageTracker.create_calculated(
                    method="BTC_correlation_no_data",
                    dependencies=[context.data_lineage] if context.data_lineage else [],
                    quality=DataQuality.VERY_LOW,
                    metadata={'error': 'No data available on any timeframe'}
                )
                result = {
                    "error": "No data available on any timeframe",
                    "correlation": 0.0,
                    "confidence": 0.0,
                    "lineage": lineage
                }
                context.add_result(self.name, result, lineage)
                return result
            
            # Выполняем анализ на каждом таймфрейме
            tf_analysis_results = {}
            lineages = []
            
            for tf, (df_main, df_btc, lineage) in tf_data.items():
                tf_result = self._analyze_single_timeframe(
                    symbol, tf, df_main, df_btc, lineage, context
                )
                if tf_result and 'error' not in tf_result:
                    tf_analysis_results[tf] = tf_result
                    if tf_result.get('lineage'):
                        lineages.append(tf_result['lineage'])
            
            if not tf_analysis_results:
                lineage = LineageTracker.create_calculated(
                    method="BTC_correlation_analysis_failed",
                    dependencies=[context.data_lineage] if context.data_lineage else [],
                    quality=DataQuality.LOW,
                    metadata={'error': 'Analysis failed on all timeframes'}
                )
                result = {
                    "error": "Analysis failed on all timeframes",
                    "correlation": 0.0,
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
                trend = 1 if result.get('btc_trend') == 'BULLISH' else (-1 if result.get('btc_trend') == 'BEARISH' else 0)
                tf_analysis_for_aggregator[tf] = {
                    'trend': trend,
                    'trend_strength': abs(result.get('correlation', 0)),
                    'support': 0,  # BTC correlation не предоставляет уровни
                    'resistance': 0,
                    'volume_score': result.get('confidence', 0),
                    'atr': 0,
                    'confidence': result.get('confidence', 0)
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
                "correlation": multi_tf_context.trend_alignment,  # Используем alignment как aggregate correlation
                "influence": self._classify_influence(multi_tf_context.trend_alignment),
                "confidence": multi_tf_context.composite_confidence,
                "lineage": multi_tf_context.lineage
            }
            
            context.add_result(self.name, final_result, multi_tf_context.lineage)
            return final_result

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
    
    def _collect_all_timeframe_data(self, context: AnalysisContext, symbol: str) -> Dict[str, Tuple]:
        """
        Собирает данные со всех доступных таймфреймов (базовых + синтетических).
        Returns: dict {timeframe: (df_main, df_btc, lineage)}
        """
        tf_data = {}
        
        # Проверяем базовые market data
        base_df = context.get_data(DataSource.MARKET_DATA, symbol=symbol)
        if base_df is not None and not base_df.empty:
            tf_data[context.timeframe] = (base_df, None, context.data_lineage)
        
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
                tf_data[tf] = (synthetic_df, None, synthetic_lineage)
        
        return tf_data
    
    def _analyze_single_timeframe(self, symbol: str, tf: str, df_main: pd.DataFrame, 
                                   df_btc: Optional[pd.DataFrame], lineage, 
                                   context: AnalysisContext) -> Dict:
        """
        Анализирует корреляцию на одном таймфрейме.
        """
        if df_main is None or df_main.empty:
            return {"error": f"No data for {tf}", "confidence": 0.0}

        # Определяем базовый актив
        base_asset = symbol.replace('USDT', '').replace('BUSD', '')
        btc_symbol = "BTCUSDT"
        
        # Если это сам BTC, корреляция 1.0
        if base_asset == "BTC":
            result_lineage = LineageTracker.create_calculated(
                method="BTC_direct_correlation",
                dependencies=[lineage] if lineage else [],
                quality=DataQuality.HIGH,
                metadata={'correlation': 1.0, 'influence': 'DIRECT', 'timeframe': tf}
            )
            return {
                "correlation": 1.0,
                "influence": "DIRECT",
                "confidence": 1.0,
                "lag_minutes": 0,
                "btc_trend": self._determine_trend(df_main),
                "timeframe": tf,
                "lineage": result_lineage
            }

        # Загружаем данные BTC если еще не загружены
        if df_btc is None:
            end_time = df_main.index[-1]
            start_time = df_main.index[0] - timedelta(hours=24)
            df_btc = self._fetch_btc_data(btc_symbol, start_time, end_time, tf)
            
            if df_btc is None or df_btc.empty:
                return {
                    "error": "BTC data unavailable",
                    "confidence": 0.0,
                    "timeframe": tf
                }

        # Синхронизируем данные
        df_sync = self._synchronize_data(df_main, df_btc, tf)
        
        if len(df_sync) < 20:
            return {
                "error": "Insufficient synchronized data",
                "confidence": 0.0,
                "timeframe": tf
            }

        # Расчет корреляции
        corr_value, lag = self._calculate_rolling_correlation(df_sync, window=24)
        influence_type = self._classify_influence(corr_value)
        
        # Оценка уверенности
        confidence = min(1.0, abs(corr_value) * (len(df_sync) / 100))
        if len(df_sync) < 50:
            confidence *= 0.8

        btc_trend = self._determine_trend(df_sync[['close_btc']])

        result_lineage = LineageTracker.create_calculated(
            method="BTC_rolling_correlation_lag_adjusted",
            dependencies=[lineage] if lineage else [],
            quality=DataQuality.MEDIUM if len(df_sync) >= 50 else DataQuality.LOW,
            metadata={
                'correlation': corr_value,
                'lag_minutes': lag,
                'sample_size': len(df_sync),
                'btc_trend': btc_trend,
                'timeframe': tf
            }
        )

        return {
            "correlation": round(corr_value, 4),
            "influence": influence_type,
            "confidence": round(confidence, 4),
            "lag_minutes": lag,
            "btc_trend": btc_trend,
            "sample_size": len(df_sync),
            "timeframe": tf,
            "lineage": result_lineage
        }

    def _fetch_btc_data(self, symbol: str, start: datetime, end: datetime, timeframe: str = '1h') -> Optional[pd.DataFrame]:
        """Загружает свечи BTC для указанного таймфрейма."""
        try:
            # Маппинг наших TF в формат Binance
            tf_map = {
                '5m': '5m', '10m': '10m', '15m': '15m', '30m': '30m',
                '1h': '1h', '4h': '4h', '12h': '12h', '1d': '1d'
            }
            binance_tf = tf_map.get(timeframe, '1h')
            
            # В реальном проекте здесь вызов клиента с ограничением частоты
            klines = self.client.get_klines(
                symbol=symbol,
                interval=binance_tf,
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
        """
        CRITICAL: Синхронизация временных меток для корректного расчета корреляции.
        Использует .intersection() индексов для сравнения только идентичных timestamp.
        """
        # Ресемплинг к единому таймфрейму
        df_m = df_main[['close']].copy()
        df_b = df_btc.rename(columns={'close': 'close_btc'})
        
        # CRITICAL: Используем intersection для гарантии идентичных timestamp
        # Это предотвращает ложную корреляцию из-за рассинхронизации времени
        common_index = df_m.index.intersection(df_b.index)
        
        if len(common_index) < 20:
            # Если мало общих точек, используем forward fill с осторожностью
            df_merged = pd.merge_asof(
                df_m.reset_index(), 
                df_b.reset_index(), 
                on='time', 
                direction='backward'
            ).set_index('time')
        else:
            # Предпочтительный путь: только точные совпадения timestamp
            df_merged = pd.concat([
                df_m.loc[common_index],
                df_b.loc[common_index]
            ], axis=1)
        
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
