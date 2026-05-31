"""Public Binance WebSocket helpers.

The live reconnecting WS service will be added later. This module already owns
stream URL construction and message parsing into NOVA data models.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict

from nova.data.models import Candle, DataSourceRef, DataSourceType


@dataclass(frozen=True)
class BinanceWsConfig:
    base_url: str


class BinanceWsClient:
    def __init__(self, config: BinanceWsConfig) -> None:
        self.config = config
        self.base_url = config.base_url.rstrip("/")

    def kline_stream_url(self, symbol: str, interval: str) -> str:
        return f"{self.base_url}/{symbol.lower()}@kline_{interval}"

    def parse_kline_message(self, message: str | Dict[str, Any]) -> Candle:
        payload = json.loads(message) if isinstance(message, str) else message
        data = payload.get("data", payload)
        kline = data.get("k")
        if not isinstance(kline, dict):
            raise ValueError("Binance WS message does not contain kline payload")
        symbol = str(kline["s"]).upper()
        interval = str(kline["i"])
        source = DataSourceRef(
            source_type=DataSourceType.BINANCE_WS,
            source_id="binance_ws_kline",
            endpoint=self.kline_stream_url(symbol, interval),
            symbol=symbol,
            timeframe=interval,
            payload={"event_type": data.get("e")},
        )
        return Candle(
            symbol=symbol,
            timeframe=interval,
            open_time=_millis_to_iso(int(kline["t"])),
            close_time=_millis_to_iso(int(kline["T"])),
            open=float(kline["o"]),
            high=float(kline["h"]),
            low=float(kline["l"]),
            close=float(kline["c"]),
            volume=float(kline["v"]),
            quote_volume=float(kline["q"]) if "q" in kline else None,
            trade_count=int(kline["n"]) if "n" in kline else None,
            taker_buy_base_volume=float(kline["V"]) if "V" in kline else None,
            taker_buy_quote_volume=float(kline["Q"]) if "Q" in kline else None,
            source=source,
            is_closed=bool(kline.get("x", False)),
            payload={"event_time": data.get("E")},
        )


def _millis_to_iso(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()
