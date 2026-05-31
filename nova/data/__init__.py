"""Data access contracts and caches.

Raw external payloads must be adapted into NOVA data models before analyzers
consume them.

REST warmup fills the rolling cache and produces MarketSnapshot objects; WS later
updates the cache through parsed public stream messages.
"""
