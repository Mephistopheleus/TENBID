"""Data Manager - handles fetching and caching of market data"""
import pandas as pd
from datetime import datetime
from core.data_lineage import LineageTracker, DataSource, DataQuality, DataLineage

class DataManager:
    def __init__(self, config, binance_connector):
        self.binance = binance_connector
        self.symbol = config.get('GENERAL', 'symbol')
        self.warmup_candles = config.getint('DATA', 'warmup_candles')
        self.base_timeframe = config.get('DATA', 'base_timeframe')
        
        # Маркировка для последних загруженных данных
        self._last_lineage = None
    
    async def load_warmup_data(self):
        """Load historical data for warmup"""
        klines = await self.binance.get_klines(
            symbol=self.symbol,
            interval=self.base_timeframe,
            limit=self.warmup_candles
        )
        df = self._parse_klines(klines)
        
        # Создаем маркировку для сырых данных
        self._last_lineage = LineageTracker.create_from_source(
            source=DataSource.BINANCE_API,
            quality=DataQuality.HIGH,
            metadata={
                'candles_count': len(df),
                'timeframe': self.base_timeframe,
                'symbol': self.symbol
            }
        )
        
        return df, self._last_lineage
    
    async def fetch_latest(self, limit=50):
        """Fetch latest candles"""
        klines = await self.binance.get_klines(
            symbol=self.symbol,
            interval=self.base_timeframe,
            limit=limit
        )
        df = self._parse_klines(klines)
        
        # Обновляем маркировку
        self._last_lineage = LineageTracker.create_from_source(
            source=DataSource.BINANCE_API,
            quality=DataQuality.HIGH,
            metadata={
                'candles_count': len(df),
                'timeframe': self.base_timeframe,
                'symbol': self.symbol
            }
        )
        
        return df, self._last_lineage
    
    def get_last_lineage(self):
        """Получить последнюю маркировку данных"""
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

