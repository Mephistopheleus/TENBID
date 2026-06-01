"""Rate-limited orderbook access.

Orderbook is short-lived context. Normal runtime reads it no more often than a
TTL policy allows; urgent callers may force a fresh fetch when precise current
liquidity is needed, for example to refine slippage around closing/resolution.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Dict, Tuple

from nova.data.binance_rest import BinanceRestClient
from nova.data.models import OrderbookSnapshot


@dataclass(frozen=True)
class OrderbookCacheResult:
    snapshot: OrderbookSnapshot
    fetched: bool
    cache_age_sec: float
    reason: str
    forced: bool = False


class RateLimitedOrderbookCache:
    def __init__(self, ttl_sec: float = 10.0) -> None:
        self.ttl_sec = max(0.0, ttl_sec)
        self._items: Dict[Tuple[str, int], Tuple[OrderbookSnapshot, float]] = {}

    def get_orderbook(
        self,
        rest_client: BinanceRestClient,
        symbol: str,
        limit: int,
        *,
        force_refresh: bool = False,
        reason: str = "context_refresh",
    ) -> OrderbookCacheResult:
        key = (symbol.upper(), limit)
        cached = self._items.get(key)
        age = self._age(cached)
        if cached is not None and not force_refresh and age < self.ttl_sec:
            return OrderbookCacheResult(
                snapshot=cached[0],
                fetched=False,
                cache_age_sec=age,
                reason=reason,
            )

        snapshot = rest_client.get_orderbook(symbol, limit=limit)
        self._items[key] = (snapshot, monotonic())
        return OrderbookCacheResult(
            snapshot=snapshot,
            fetched=True,
            cache_age_sec=0.0,
            reason=reason,
            forced=force_refresh,
        )

    @staticmethod
    def _age(cached: Tuple[OrderbookSnapshot, float] | None) -> float:
        if cached is None:
            return float("inf")
        return monotonic() - cached[1]
