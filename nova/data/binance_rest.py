"""Read-only Binance REST adapter.

This client is for public market data only: warmup candles, reconciliation,
orderbook probes and price checks. It adapts exchange JSON into NOVA data models.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from nova.data.models import (
    Candle,
    CandleSeries,
    DataQualityReport,
    DataSourceRef,
    DataSourceType,
    OrderbookLevel,
    OrderbookSnapshot,
    utc_now,
)


class BinanceMarketType:
    SPOT = "SPOT"
    USD_M_FUTURES = "USD_M_FUTURES"


@dataclass(frozen=True)
class BinanceRestConfig:
    base_url: str
    market_type: str = BinanceMarketType.USD_M_FUTURES
    timeout_sec: float = 10.0


class BinanceRestClient:
    def __init__(self, config: BinanceRestConfig) -> None:
        self.config = config
        self.base_url = config.base_url.rstrip("/")

    def ping(self) -> bool:
        self._get(self._path("ping"))
        return True

    def server_time(self) -> Dict[str, Any]:
        payload = self._get(self._path("time"))
        if not isinstance(payload, dict):
            raise ValueError("Unexpected Binance time response")
        return payload

    def get_ticker_price(self, symbol: str) -> float:
        payload = self._get(self._path("ticker/price"), {"symbol": symbol.upper()})
        if not isinstance(payload, dict) or "price" not in payload:
            raise ValueError("Unexpected Binance ticker response")
        return float(payload["price"])

    def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 300,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> CandleSeries:
        symbol = symbol.upper()
        params: Dict[str, Any] = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_time_ms is not None:
            params["startTime"] = start_time_ms
        if end_time_ms is not None:
            params["endTime"] = end_time_ms
        payload = self._get(self._path("klines"), params)
        if not isinstance(payload, list):
            raise ValueError("Unexpected Binance klines response")
        source = DataSourceRef(
            source_type=DataSourceType.BINANCE_REST,
            source_id="binance_rest_klines",
            endpoint=self._path("klines"),
            symbol=symbol,
            timeframe=interval,
            payload={
                "market_type": self.config.market_type,
                "limit": limit,
                "start_time_ms": start_time_ms,
                "end_time_ms": end_time_ms,
            },
        )
        candles = [self._kline_to_candle(symbol, interval, row, source) for row in payload]
        quality = DataQualityReport(
            is_usable=bool(candles),
            score=1.0 if candles else 0.0,
            completeness=min(1.0, len(candles) / max(1, limit)),
            issue_codes=[] if candles else ["empty_klines"],
        )
        return CandleSeries(symbol=symbol, timeframe=interval, candles=candles, source=source, quality=quality)

    def get_orderbook(self, symbol: str, limit: int = 20) -> OrderbookSnapshot:
        symbol = symbol.upper()
        payload = self._get(self._path("depth"), {"symbol": symbol, "limit": limit})
        if not isinstance(payload, dict):
            raise ValueError("Unexpected Binance orderbook response")
        source = DataSourceRef(
            source_type=DataSourceType.BINANCE_REST,
            source_id="binance_rest_depth",
            endpoint=self._path("depth"),
            symbol=symbol,
            payload={"market_type": self.config.market_type, "limit": limit},
        )
        bids = [OrderbookLevel(price=float(price), quantity=float(quantity)) for price, quantity in payload.get("bids", [])]
        asks = [OrderbookLevel(price=float(price), quantity=float(quantity)) for price, quantity in payload.get("asks", [])]
        return OrderbookSnapshot(
            symbol=symbol,
            event_time=utc_now(),
            bids=bids,
            asks=asks,
            source=source,
            last_update_id=payload.get("lastUpdateId"),
            limit=limit,
            quality=DataQualityReport(is_usable=bool(bids and asks), score=1.0 if bids and asks else 0.0),
            payload={"raw_keys": sorted(payload.keys())},
        )

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        query = f"?{urlencode(params)}" if params else ""
        request = Request(f"{self.base_url}{path}{query}", headers={"User-Agent": "NOVA/0.1"})
        with urlopen(request, timeout=self.config.timeout_sec) as response:
            return json.loads(response.read().decode("utf-8"))

    def _path(self, name: str) -> str:
        prefix = "/api/v3" if self.config.market_type == BinanceMarketType.SPOT else "/fapi/v1"
        return f"{prefix}/{name}"

    @staticmethod
    def _kline_to_candle(symbol: str, interval: str, row: List[Any], source: DataSourceRef) -> Candle:
        return Candle(
            symbol=symbol,
            timeframe=interval,
            open_time=_millis_to_iso(int(row[0])),
            close_time=_millis_to_iso(int(row[6])),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
            quote_volume=float(row[7]) if len(row) > 7 else None,
            trade_count=int(row[8]) if len(row) > 8 else None,
            taker_buy_base_volume=float(row[9]) if len(row) > 9 else None,
            taker_buy_quote_volume=float(row[10]) if len(row) > 10 else None,
            source=source,
            is_closed=True,
            payload={"raw_length": len(row)},
        )


def _millis_to_iso(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()
