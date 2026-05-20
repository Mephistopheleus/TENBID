"""Binance Connector - PC/BC for Testnet and Live"""
import hashlib
import hmac
import time
import aiohttp
import logging
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

class BinanceConnector:
    def __init__(self, config):
        self.mode = config.get('GENERAL', 'mode', fallback='TESTNET')
        if self.mode == 'TESTNET':
            self.api_key = config.get('BINANCE_TESTNET', 'api_key')
            self.secret_key = config.get('BINANCE_TESTNET', 'secret_key')
            self.base_url = config.get('BINANCE_TESTNET', 'base_url')
        else:
            self.api_key = config.get('BINANCE_LIVE', 'api_key')
            self.secret_key = config.get('BINANCE_LIVE', 'secret_key')
            self.base_url = config.get('BINANCE_LIVE', 'base_url')
        
        self.session = None
        self.symbol = config.get('GENERAL', 'symbol', fallback='DOGEUSDT')
    
    async def connect(self):
        self.session = aiohttp.ClientSession()
        # Test connection
        try:
            await self._request('GET', '/fapi/v1/time', signed=False)
            return True
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Binance Futures: {e}")
    
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
        return await self._request('GET', '/fapi/v1/klines', params=params, signed=False)
    
    async def get_ticker_price(self, symbol=None):
        """Get current price"""
        params = {'symbol': symbol or self.symbol}
        return await self._request('GET', '/fapi/v1/ticker/price', params=params, signed=False)
    
    async def get_account_balance(self):
        """Get account balance (Futures)"""
        return await self._request('GET', '/fapi/v2/balance', signed=True)
    
    async def place_order(self, side, quantity, price=None, order_type='LIMIT'):
        """Place a trade order (Market/Limit) for Futures"""
        params = {
            'symbol': self.symbol,
            'side': side.upper(),
            'type': order_type.upper(),
            'quantity': self._format_quantity(quantity),
        }
        
        # Add price for LIMIT orders
        if order_type.upper() == 'LIMIT' and price:
            params['price'] = self._format_price(price)
            params['timeInForce'] = 'GTC'
        
        try:
            result = await self._request('POST', '/fapi/v1/order', params=params, signed=True)
            logger.info(f"Futures Order placed: {side} {quantity} {self.symbol} @ {price or 'MARKET'}")
            return result
        except Exception as e:
            logger.error(f"Failed to place futures order: {e}")
            raise
    
    async def place_market_order(self, side, quantity):
        """Place a MARKET order for immediate execution"""
        return await self.place_order(side, quantity, order_type='MARKET')
    
    async def get_order_status(self, order_id):
        """Get order status by ID (Futures)"""
        params = {
            'symbol': self.symbol,
            'orderId': order_id
        }
        return await self._request('GET', '/fapi/v1/order', params=params, signed=True)
    
    def _format_quantity(self, qty):
        """Format quantity according to Binance LOT_SIZE rules"""
        # For most pairs: 6 decimal places, adjust based on symbol info if needed
        return f"{qty:.6f}"
    
    def _format_price(self, price):
        """Format price according to Binance PRICE_FILTER rules"""
        # For most pairs: 2 decimal places, adjust based on symbol info
        return f"{price:.2f}"
    
    async def cancel_order(self, order_id):
        """Cancel an order (Futures)"""
        params = {
            'symbol': self.symbol,
            'orderId': order_id
        }
        return await self._request('DELETE', '/fapi/v1/order', params=params, signed=True)
    
    async def get_open_orders(self):
        """Get open orders (Futures)"""
        params = {'symbol': self.symbol}
        return await self._request('GET', '/fapi/v1/openOrders', params=params, signed=True)
    
    async def get_order_book(self, symbol=None, limit=20):
        """Get order book (depth) for Futures"""
        params = {
            'symbol': symbol or self.symbol,
            'limit': limit
        }
        return await self._request('GET', '/fapi/v1/depth', params=params, signed=False)
    
    async def get_account_commission(self, symbol=None):
        """Get trading commission rates for the account (Futures)"""
        try:
            # Get account trade fees - use v2 endpoint for Testnet compatibility
            data = await self._request('GET', '/fapi/v2/account', params={}, signed=True)
            
            # Extract commission rates for the specific symbol if available
            if 'symbols' in data and isinstance(data['symbols'], list):
                for sym_data in data['symbols']:
                    if sym_data.get('symbol') == (symbol or self.symbol):
                        maker_fee = float(sym_data.get('makerFeeRate', 0.0002))
                        taker_fee = float(sym_data.get('takerFeeRate', 0.0004))
                        return {
                            'maker': maker_fee,
                            'taker': taker_fee,
                            'symbol': symbol or self.symbol
                        }
            
            # Fallback to account-level fees if symbol-specific not found
            maker_fee = float(data.get('makerFeeRate', 0.0002))
            taker_fee = float(data.get('takerFeeRate', 0.0004))
            return {
                'maker': maker_fee,
                'taker': taker_fee,
                'symbol': symbol or self.symbol
            }
        except Exception as e:
            logger.warning(f"Could not fetch commission rates, using defaults: {e}")
            # Default futures fees: 0.02% maker, 0.04% taker
            return {
                'maker': 0.0002,
                'taker': 0.0004,
                'symbol': symbol or self.symbol
            }
    
    async def get_symbol_info(self, symbol=None):
        """Get symbol info including filters for precision and limits (Futures)"""
        try:
            data = await self._request('GET', '/fapi/v1/exchangeInfo', params={}, signed=False)
            
            for sym_data in data.get('symbols', []):
                if sym_data['symbol'] == (symbol or self.symbol):
                    return sym_data
            
            return None
        except Exception as e:
            logger.warning(f"Could not fetch symbol info: {e}")
            return None
    
    async def estimate_slippage(self, side, quantity, symbol=None, depth_limit=20):
        """
        Estimate slippage based on current orderbook depth.
        Returns estimated slippage percentage and price impact.
        """
        try:
            ob = await self.get_order_book(symbol=symbol, limit=depth_limit)
            current_price = float(ob['bids'][0][0]) if ob.get('bids') else 0
            
            if current_price == 0:
                return {'slippage_pct': 0.001, 'price_impact': 0.0, 'estimated_price': current_price}
            
            total_qty = 0
            weighted_price = 0
            levels_to_check = ob['asks'] if side.upper() == 'BUY' else ob['bids']
            
            for level in levels_to_check:
                price = float(level[0])
                qty = float(level[1])
                
                if total_qty + qty >= quantity:
                    remaining = quantity - total_qty
                    weighted_price += price * remaining
                    total_qty = quantity
                    break
                else:
                    weighted_price += price * qty
                    total_qty += qty
            
            if total_qty < quantity:
                # Not enough liquidity, add penalty
                avg_price = weighted_price / total_qty if total_qty > 0 else current_price
                slippage_pct = abs(avg_price - current_price) / current_price + 0.001
            else:
                avg_price = weighted_price / quantity
                slippage_pct = abs(avg_price - current_price) / current_price
            
            return {
                'slippage_pct': max(slippage_pct, 0.0005),  # Minimum 0.05%
                'price_impact': slippage_pct,
                'estimated_price': avg_price if side.upper() == 'BUY' else avg_price
            }
        except Exception as e:
            logger.warning(f"Could not estimate slippage, using default: {e}")
            return {'slippage_pct': 0.001, 'price_impact': 0.001, 'estimated_price': 0}
