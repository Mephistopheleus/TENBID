"""Binance Connector - PC/BC for Testnet and Live"""
import hashlib
import hmac
import time
import aiohttp
from urllib.parse import urlencode

class BinanceConnector:
    def __init__(self, config):
        self.mode = config.get('GENERAL', 'mode')
        if self.mode == 'TESTNET':
            self.api_key = config.get('BINANCE_TESTNET', 'api_key')
            self.secret_key = config.get('BINANCE_TESTNET', 'secret_key')
            self.base_url = config.get('BINANCE_TESTNET', 'base_url')
        else:
            self.api_key = config.get('BINANCE_LIVE', 'api_key')
            self.secret_key = config.get('BINANCE_LIVE', 'secret_key')
            self.base_url = config.get('BINANCE_LIVE', 'base_url')
        
        self.session = None
        self.symbol = config.get('GENERAL', 'symbol')
    
    async def connect(self):
        self.session = aiohttp.ClientSession()
        # Test connection
        try:
            await self._request('GET', '/api/v3/time', signed=False)
            return True
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Binance: {e}")
    
    async def close(self):
        if self.session:
            await self.session.close()
    
    def _generate_signature(self, query_string):
        return hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    async def _request(self, method, endpoint, params=None, signed=True):
        url = f"{self.base_url}{endpoint}"
        
        if params is None:
            params = {}
        
        if signed:
            params['timestamp'] = int(time.time() * 1000)
            query_string = urlencode(params)
            params['signature'] = self._generate_signature(query_string)
        
        headers = {'X-MBX-APIKEY': self.api_key}
        
        async with self.session.request(method, url, params=params, headers=headers) as response:
            data = await response.json()
            if response.status != 200:
                raise Exception(f"Binance API Error: {data}")
            return data
    
    async def get_klines(self, symbol=None, interval='5m', limit=300):
        """Get candlestick data"""
        params = {
            'symbol': symbol or self.symbol,
            'interval': interval,
            'limit': limit
        }
        return await self._request('GET', '/api/v3/klines', params=params, signed=False)
    
    async def get_ticker_price(self, symbol=None):
        """Get current price"""
        params = {'symbol': symbol or self.symbol}
        return await self._request('GET', '/api/v3/ticker/price', params=params, signed=False)
    
    async def get_account_balance(self):
        """Get account balance"""
        return await self._request('GET', '/api/v3/account', signed=True)
    
    async def place_order(self, side, quantity, price=None, order_type='LIMIT'):
        """Place a trade order"""
        params = {
            'symbol': self.symbol,
            'side': side.upper(),
            'type': order_type.upper(),
            'quantity': quantity,
            'timeInForce': 'GTC'
        }
        
        if price and order_type == 'LIMIT':
            params['price'] = price
        
        return await self._request('POST', '/api/v3/order', params=params, signed=True)
    
    async def cancel_order(self, order_id):
        """Cancel an order"""
        params = {
            'symbol': self.symbol,
            'orderId': order_id
        }
        return await self._request('DELETE', '/api/v3/order', params=params, signed=True)
    
    async def get_open_orders(self):
        """Get open orders"""
        params = {'symbol': self.symbol}
        return await self._request('GET', '/api/v3/openOrders', params=params, signed=True)
