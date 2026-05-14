"""
TENBID - Binance Connector Module (PC/BC)
Handles connection to Binance Testnet/Live with order management
"""

import hashlib
import hmac
import time
import requests
from typing import Dict, List, Optional
from urllib.parse import urlencode

class BinanceConnector:
    def __init__(self, api_key: str, secret_key: str, testnet: bool = True):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = "https://testnet.binance.vision" if testnet else "https://api.binance.com"
        self.session = requests.Session()
        self.session.headers.update({
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded"
        })
        self.recv_window = 5000
        
    def _generate_signature(self, params: Dict) -> str:
        """Generate HMAC SHA256 signature"""
        query_string = urlencode(params)
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _get_timestamp(self) -> int:
        """Get current timestamp in milliseconds"""
        return int(time.time() * 1000)
    
    def _request(self, method: str, endpoint: str, params: Dict = None, signed: bool = False) -> Dict:
        """Make authenticated or public request"""
        url = f"{self.base_url}{endpoint}"
        
        if params is None:
            params = {}
        
        if signed:
            params['timestamp'] = self._get_timestamp()
            params['recvWindow'] = self.recv_window
            params['signature'] = self._generate_signature(params)
        
        try:
            response = self.session.request(method, url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Request error: {e}")
            return {"error": str(e)}
    
    def get_account_balance(self) -> Dict:
        """Get account balance information"""
        return self._request("GET", "/api/v3/account", signed=True)
    
    def get_symbol_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol"""
        data = self._request("GET", "/api/v3/ticker/price", {"symbol": symbol})
        if "price" in data:
            return float(data["price"])
        return None
    
    def get_klines(self, symbol: str, interval: str, limit: int = 100) -> List[List]:
        """Get candlestick data"""
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        data = self._request("GET", "/api/v3/klines", params)
        return data if isinstance(data, list) else []
    
    def place_order(self, symbol: str, side: str, order_type: str, 
                    quantity: float, price: Optional[float] = None,
                    stop_loss: Optional[float] = None, 
                    take_profit: Optional[float] = None) -> Dict:
        """Place a new order with optional SL/TP"""
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": quantity,
        }
        
        if order_type.upper() == "LIMIT":
            if price is None:
                return {"error": "Price required for LIMIT order"}
            params["price"] = price
            params["timeInForce"] = "GTC"
        
        result = self._request("POST", "/api/v3/order", params, signed=True)
        
        # Place stop loss and take profit orders if specified
        if "orderId" in result and (stop_loss or take_profit):
            order_id = result["orderId"]
            entry_price = price if price else float(result.get("fills", [{}])[0].get("price", 0))
            
            if stop_loss:
                sl_params = {
                    "symbol": symbol,
                    "side": "SELL" if side.upper() == "BUY" else "BUY",
                    "type": "STOP_LOSS_LIMIT",
                    "quantity": quantity,
                    "price": stop_loss,
                    "stopPrice": stop_loss,
                    "timeInForce": "GTC"
                }
                self._request("POST", "/api/v3/order", sl_params, signed=True)
            
            if take_profit:
                tp_params = {
                    "symbol": symbol,
                    "side": "SELL" if side.upper() == "BUY" else "BUY",
                    "type": "TAKE_PROFIT_LIMIT",
                    "quantity": quantity,
                    "price": take_profit,
                    "stopPrice": take_profit,
                    "timeInForce": "GTC"
                }
                self._request("POST", "/api/v3/order", tp_params, signed=True)
        
        return result
    
    def cancel_order(self, symbol: str, order_id: int) -> Dict:
        """Cancel an existing order"""
        params = {"symbol": symbol, "orderId": order_id}
        return self._request("DELETE", "/api/v3/order", params, signed=True)
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Get all open orders"""
        params = {}
        if symbol:
            params["symbol"] = symbol
        data = self._request("GET", "/api/v3/openOrders", params, signed=True)
        return data if isinstance(data, list) else []
    
    def get_order_status(self, symbol: str, order_id: int) -> Dict:
        """Get order status"""
        params = {"symbol": symbol, "orderId": order_id}
        return self._request("GET", "/api/v3/order", params, signed=True)
    
    def switch_mode(self, to_live: bool):
        """Switch between testnet and live trading"""
        if to_live:
            self.base_url = "https://api.binance.com"
            print("⚠️  SWITCHED TO LIVE TRADING MODE ⚠️")
        else:
            self.base_url = "https://testnet.binance.vision"
            print("✓ Switched to TESTNET mode")


if __name__ == "__main__":
    # Test connection
    connector = BinanceConnector(
        api_key="mYVqkHL4mSwEiHrHC6PaurPUHOV7auYwXXpkSmMX7hSSY8KT7teRmbQV6BY9YD3i",
        secret_key="ym3B6HkI6ervEsc4We0jr47O51tueW8CRTqpU6TxbpwzKsxAtLWtGKtbeUQ86aBf",
        testnet=True
    )
    
    print("Testing Binance Connection...")
    balance = connector.get_account_balance()
    print(f"Account Balance: {balance}")
    
    price = connector.get_symbol_price("BTCUSDT")
    print(f"BTCUSDT Price: {price}")
    
    klines = connector.get_klines("BTCUSDT", "1m", limit=5)
    print(f"Latest Klines: {len(klines)} candles")
