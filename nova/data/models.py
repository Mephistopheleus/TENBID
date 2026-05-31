"""Canonical market data contracts.

Binance REST/WS clients and future data sources must adapt raw payloads into
these NOVA models before analyzers see them. Analyzers should not depend on
exchange-specific JSON shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from nova.core.ids import new_id


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DataSourceType:
    BINANCE_REST = "BINANCE_REST"
    BINANCE_WS = "BINANCE_WS"
    SYNTHETIC = "SYNTHETIC"
    INTERNAL = "INTERNAL"
    RSS = "RSS"
    FIXTURE = "FIXTURE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class DataSourceRef:
    source_type: str
    source_id: str
    retrieved_at: str = field(default_factory=utc_now)
    endpoint: Optional[str] = None
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DataQualityReport:
    is_usable: bool
    score: float
    completeness: float = 1.0
    freshness_sec: Optional[float] = None
    gap_count: int = 0
    issue_codes: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def unknown(cls, reason: str = "not_evaluated") -> "DataQualityReport":
        return cls(
            is_usable=False,
            score=0.0,
            completeness=0.0,
            issue_codes=[reason],
            notes=["Data quality has not been evaluated yet."],
        )

    @classmethod
    def good(cls) -> "DataQualityReport":
        return cls(is_usable=True, score=1.0, completeness=1.0)


@dataclass(frozen=True)
class Candle:
    symbol: str
    timeframe: str
    open_time: str
    close_time: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: DataSourceRef
    is_closed: bool = True
    quote_volume: Optional[float] = None
    trade_count: Optional[int] = None
    taker_buy_base_volume: Optional[float] = None
    taker_buy_quote_volume: Optional[float] = None
    candle_id: str = field(default_factory=lambda: new_id("CANDLE"))
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CandleSeries:
    symbol: str
    timeframe: str
    candles: List[Candle]
    source: DataSourceRef
    quality: DataQualityReport = field(default_factory=DataQualityReport.good)
    series_id: str = field(default_factory=lambda: new_id("CANDLE_SERIES"))
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.candles)

    def latest_closed(self) -> Optional[Candle]:
        for candle in reversed(self.candles):
            if candle.is_closed:
                return candle
        return None


@dataclass(frozen=True)
class OrderbookLevel:
    price: float
    quantity: float


@dataclass(frozen=True)
class OrderbookSnapshot:
    symbol: str
    event_time: str
    bids: List[OrderbookLevel]
    asks: List[OrderbookLevel]
    source: DataSourceRef
    last_update_id: Optional[int] = None
    limit: Optional[int] = None
    quality: DataQualityReport = field(default_factory=DataQualityReport.good)
    snapshot_id: str = field(default_factory=lambda: new_id("ORDERBOOK"))
    payload: Dict[str, Any] = field(default_factory=dict)

    def best_bid(self) -> Optional[OrderbookLevel]:
        return self.bids[0] if self.bids else None

    def best_ask(self) -> Optional[OrderbookLevel]:
        return self.asks[0] if self.asks else None


@dataclass(frozen=True)
class AggTrade:
    symbol: str
    trade_id: str
    event_time: str
    price: float
    quantity: float
    is_buyer_maker: bool
    source: DataSourceRef
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AggTradeSeries:
    symbol: str
    trades: List[AggTrade]
    source: DataSourceRef
    quality: DataQualityReport = field(default_factory=DataQualityReport.good)
    series_id: str = field(default_factory=lambda: new_id("AGG_TRADES"))
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.trades)


@dataclass(frozen=True)
class FundingRate:
    symbol: str
    event_time: str
    funding_rate: float
    source: DataSourceRef
    next_funding_time: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OpenInterestPoint:
    symbol: str
    event_time: str
    open_interest: float
    source: DataSourceRef
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LongShortRatioPoint:
    symbol: str
    event_time: str
    long_short_ratio: float
    source: DataSourceRef
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DerivativesSnapshot:
    symbol: str
    event_time: str
    source: DataSourceRef
    funding_rate: Optional[FundingRate] = None
    open_interest: Optional[OpenInterestPoint] = None
    long_short_ratio: Optional[LongShortRatioPoint] = None
    quality: DataQualityReport = field(default_factory=DataQualityReport.unknown)
    snapshot_id: str = field(default_factory=lambda: new_id("DERIVATIVES"))
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NewsItem:
    title: str
    summary: str
    source_name: str
    published_at: str
    url: str
    source: DataSourceRef
    symbols: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    sentiment_score: float = 0.0
    impact_score: float = 0.0
    item_id: str = field(default_factory=lambda: new_id("NEWS"))
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NewsBatch:
    items: List[NewsItem]
    source: DataSourceRef
    quality: DataQualityReport = field(default_factory=DataQualityReport.unknown)
    batch_id: str = field(default_factory=lambda: new_id("NEWS_BATCH"))
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketSnapshot:
    primary_symbol: str
    base_timeframe: str
    candles: Dict[str, CandleSeries] = field(default_factory=dict)
    related_candles: Dict[str, Dict[str, CandleSeries]] = field(default_factory=dict)
    orderbook: Optional[OrderbookSnapshot] = None
    agg_trades: Optional[AggTradeSeries] = None
    derivatives: Optional[DerivativesSnapshot] = None
    news: Optional[NewsBatch] = None
    quality: DataQualityReport = field(default_factory=DataQualityReport.unknown)
    created_at: str = field(default_factory=utc_now)
    snapshot_id: str = field(default_factory=lambda: new_id("SNAPSHOT"))
    payload: Dict[str, Any] = field(default_factory=dict)

    def candle_series(self, timeframe: str, symbol: Optional[str] = None) -> Optional[CandleSeries]:
        if symbol is None or symbol == self.primary_symbol:
            return self.candles.get(timeframe)
        return self.related_candles.get(symbol, {}).get(timeframe)

