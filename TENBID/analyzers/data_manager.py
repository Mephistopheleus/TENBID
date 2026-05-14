"""Data Manager - handles fetching and caching of market data"""
import pandas as pd

class DataManager:
    def __init__(self, config, binance_connector):
        self.binance = binance_connector
        self.symbol = config.get('GENERAL', 'symbol')
        self.warmup_candles = config.getint('DATA', 'warmup_candles')
        self.base_timeframe = config.get('DATA', 'base_timeframe')
    
    async def load_warmup_data(self):
        """Load historical data for warmup"""
        klines = await self.binance.get_klines(
            symbol=self.symbol,
            interval=self.base_timeframe,
            limit=self.warmup_candles
        )
        return self._parse_klines(klines)
    
    async def fetch_latest(self, limit=50):
        """Fetch latest candles"""
        klines = await self.binance.get_klines(
            symbol=self.symbol,
            interval=self.base_timeframe,
            limit=limit
        )
        return self._parse_klines(klines)
    
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

