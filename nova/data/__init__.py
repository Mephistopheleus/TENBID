"""Data access contracts and caches.

Raw external payloads must be adapted into NOVA data models before analyzers
consume them.

REST warmup fills the rolling cache and produces MarketSnapshot objects; public
WS kline updates then refresh the cache with closed base-timeframe candles under
bounded reconnect/backoff policy.
"""
