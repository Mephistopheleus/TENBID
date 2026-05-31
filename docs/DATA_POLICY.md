# Data Policy

## Principle

Strategy thinks on 5m+ context. Microdata is used for confirmation and outcome resolution only.

## Sources

- WS 5m kline: primary live candle feed.
- REST klines: warmup, backfill, gap recovery, post-WS cache reconciliation and native TF reconciliation.
- Synthetic TF: built locally from 5m.
- Orderbook: on demand / TTL / rate-limited, not every cycle.
- AggTrades or 1m klines: only for intrabar resolution or ambiguous shadow/real outcomes.

## No analyzer direct API access

Analyzers must read from local caches and snapshots, not call Binance directly.

## REST/WS reconciliation

Runtime uses REST warmup first, then WS closed-kline updates for live cache movement. Before `CycleRunner`, recent base-TF candles are fetched again via REST, reconciled into `CandleCache`, synthetic TF are rebuilt, and a refreshed `MarketSnapshot` is logged. REST remains the control/backfill layer; WS is not the only source of truth.

## Intrabar resolution

If a 5m candle hits both TP and SL, the outcome is ambiguous until resolved by 1m or aggTrades replay. If unresolved, mark `AMBIGUOUS` and lower learning confidence.
