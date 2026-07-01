"""Data Manager - handles fetching and caching of market data across multiple timeframes"""
import pandas as pd
from datetime import datetime
from core.data_lineage import DataLineageManager, LineageNode, DataSource, DataQuality, LineageTracker

class DataManager:
    def __init__(self, config, binance_connector):
        self.binance = binance_connector
        self.symbol = config.get('GENERAL', 'symbol')
        self.warmup_candles = config.getint('DATA', 'warmup_candles')
        self.base_timeframe = config.get('DATA', 'base_timeframe')
        
        # Multi-timeframe configuration
        self.timeframes = config.get_list('DATA', 'timeframes', fallback=['5m'])
        
        # Маркировка для последних загруженных данных
        self._last_lineage = {}  # Dict per timeframe
    
    async def load_warmup_data(self):
        """Load historical data for warmup on all configured timeframes"""
        result = {}
        
        for tf in self.timeframes:
            klines = await self.binance.get_klines(
                symbol=self.symbol,
                interval=tf,
                limit=self.warmup_candles
            )
            df = self._parse_klines(klines)
            
            # Создаем маркировку для сырых данных
            lineage = LineageTracker.create_from_source(
                source=DataSource.BINANCE_API,
                quality=DataQuality.HIGH,
                metadata={
                    'candles_count': len(df),
                    'timeframe': tf,
                    'symbol': self.symbol
                }
            )
            
            result[tf] = (df, lineage)
            self._last_lineage[tf] = lineage
        
        return result
    
    async def fetch_latest(self, limit=50):
        """Fetch latest candles on all configured timeframes"""
        result = {}
        
        for tf in self.timeframes:
            klines = await self.binance.get_klines(
                symbol=self.symbol,
                interval=tf,
                limit=limit
            )
            df = self._parse_klines(klines)
            
            # Обновляем маркировку
            lineage = LineageTracker.create_from_source(
                source=DataSource.BINANCE_API,
                quality=DataQuality.HIGH,
                metadata={
                    'candles_count': len(df),
                    'timeframe': tf,
                    'symbol': self.symbol
                }
            )
            
            result[tf] = (df, lineage)
            self._last_lineage[tf] = lineage
        
        return result
    
    async def fetch_single_timeframe(self, timeframe: str, limit=50):
        """Fetch data for a single timeframe"""
        klines = await self.binance.get_klines(
            symbol=self.symbol,
            interval=timeframe,
            limit=limit
        )
        df = self._parse_klines(klines)
        
        lineage = LineageTracker.create_from_source(
            source=DataSource.BINANCE_API,
            quality=DataQuality.HIGH,
            metadata={
                'candles_count': len(df),
                'timeframe': timeframe,
                'symbol': self.symbol
            }
        )
        
        self._last_lineage[timeframe] = lineage
        return df, lineage
    
    def get_last_lineage(self, timeframe: str = None):
        """Получить последнюю маркировку данных
        
        Args:
            timeframe: Specific TF or None for all
            
        Returns:
            DataLineage or Dict[str, DataLineage]
        """
        if timeframe:
            return self._last_lineage.get(timeframe)
        return self._last_lineage
    
    def _parse_klines(self, klines):
        """Parse Binance klines to DataFrame"""
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base', 
            'taker_buy_quote', 'ignore'
        ])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        
        return df
