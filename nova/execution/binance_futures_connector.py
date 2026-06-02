"""Binance Futures connector for signed REST execution.

This is the physical exchange edge. It does not decide what to trade.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, Optional
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class BinanceFuturesConnectorConfig:
    base_url: str
    api_key: str
    secret_key: str
    timeout_sec: float = 10.0


class BinanceFuturesConnector:
    def __init__(self, config: BinanceFuturesConnectorConfig) -> None:
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self._symbol_filters: Dict[str, Dict[str, Decimal | str]] = {}

    def ping_signed(self) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v2/account", signed=True)

    def get_position_risk(self, symbol: str) -> list[Dict[str, Any]]:
        payload = self._request("GET", "/fapi/v2/positionRisk", params={"symbol": symbol.upper()}, signed=True)
        if isinstance(payload, list):
            return payload
        return [payload]

    def get_ticker_price(self, symbol: str) -> float:
        payload = self._request("GET", "/fapi/v1/ticker/price", params={"symbol": symbol.upper()}, signed=False)
        return float(payload["price"])

    def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        payload = self._request("GET", "/fapi/v1/exchangeInfo", signed=False)
        for item in payload.get("symbols", []):
            if item.get("symbol") == symbol.upper():
                return item
        raise ValueError(f"Symbol {symbol.upper()} not found in exchangeInfo")

    def get_symbol_filters(self, symbol: str) -> Dict[str, Decimal | str]:
        symbol = symbol.upper()
        if symbol in self._symbol_filters:
            return self._symbol_filters[symbol]
        info = self.get_symbol_info(symbol)
        raw_filters = {item.get("filterType"): item for item in info.get("filters", [])}
        lot = raw_filters.get("LOT_SIZE", {})
        market_lot = raw_filters.get("MARKET_LOT_SIZE", lot)
        price_filter = raw_filters.get("PRICE_FILTER", {})
        min_notional = raw_filters.get("MIN_NOTIONAL", {}) or raw_filters.get("NOTIONAL", {})
        parsed: Dict[str, Decimal | str] = {
            "symbol": symbol,
            "tick_size": Decimal(str(price_filter.get("tickSize", "0.00000001"))),
            "step_size": Decimal(str(market_lot.get("stepSize") or lot.get("stepSize", "0.00000001"))),
            "min_qty": Decimal(str(market_lot.get("minQty") or lot.get("minQty", "0"))),
            "max_qty": Decimal(str(market_lot.get("maxQty") or lot.get("maxQty", "0"))),
            "min_notional": Decimal(str(min_notional.get("notional") or min_notional.get("minNotional", "0"))),
        }
        self._symbol_filters[symbol] = parsed
        return parsed

    def prepare_market_order(
        self,
        *,
        symbol: str,
        side: str,
        notional_usdt: float,
        mark_price: Optional[float] = None,
        reduce_only: bool = False,
    ) -> Dict[str, Any]:
        symbol = symbol.upper()
        filters = self.get_symbol_filters(symbol)
        price = Decimal(str(mark_price if mark_price is not None else self.get_ticker_price(symbol)))
        if price <= 0:
            raise ValueError(f"Invalid mark price for {symbol}: {price}")

        quantity = self._floor_to_step(Decimal(str(notional_usdt)) / price, Decimal(filters["step_size"]))
        min_qty = Decimal(filters["min_qty"])
        max_qty = Decimal(filters["max_qty"])
        min_notional = Decimal(filters["min_notional"])
        if quantity < min_qty:
            raise ValueError(f"Order quantity {quantity} below minQty {min_qty} for {symbol}")
        actual_notional = quantity * price
        if min_notional > 0 and actual_notional < min_notional:
            raise ValueError(f"Order notional {actual_notional} below minNotional {min_notional} for {symbol}")
        if max_qty > 0 and quantity > max_qty:
            raise ValueError(f"Order quantity {quantity} above maxQty {max_qty} for {symbol}")

        return {
            "symbol": symbol,
            "side": side.upper(),
            "type": "MARKET",
            "quantity": self._decimal_to_str(quantity),
            "notional_usdt": float(actual_notional),
            "mark_price": float(price),
            "reduceOnly": bool(reduce_only),
            "filters": {key: self._decimal_to_str(value) if isinstance(value, Decimal) else value for key, value in filters.items()},
        }

    def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "symbol": order["symbol"],
            "side": order["side"],
            "type": order["type"],
            "quantity": order["quantity"],
            "newOrderRespType": "RESULT",
        }
        if order.get("reduceOnly"):
            params["reduceOnly"] = "true"
        return self._request("POST", "/fapi/v1/order", params=params, signed=True)

    def place_reduce_only_market_order(self, *, symbol: str, side: str, quantity: float | str) -> Dict[str, Any]:
        return self.place_order(
            {
                "symbol": symbol.upper(),
                "side": side.upper(),
                "type": "MARKET",
                "quantity": str(quantity),
                "reduceOnly": True,
            }
        )

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = True,
    ) -> Dict[str, Any]:
        params = dict(params or {})
        headers = {"User-Agent": "NOVA/0.1"}
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params["recvWindow"] = 5000
            query = urlencode(params)
            signature = hmac.new(self.config.secret_key.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
            params["signature"] = signature
            headers["X-MBX-APIKEY"] = self.config.api_key

        encoded = urlencode(params).encode("utf-8") if params else None
        url = f"{self.base_url}{path}"
        if method.upper() == "GET" and encoded:
            url = f"{url}?{encoded.decode('utf-8')}"
            encoded = None

        request = Request(url, data=encoded, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=self.config.timeout_sec) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = {"raw_body": body}
            payload["http_status"] = exc.code
            raise RuntimeError(json.dumps(payload, ensure_ascii=False)) from exc

    @staticmethod
    def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
        if step <= 0:
            return value
        return (value / step).to_integral_value(rounding=ROUND_DOWN) * step

    @staticmethod
    def _decimal_to_str(value: Decimal) -> str:
        return format(value.normalize(), "f")
