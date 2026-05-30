# Matrix Model

## Purpose

The matrix models future price zones over time. It is not a direct trading decision.

## ForecastMatrix

Answers:

- What price zone can be reached?
- Over which horizon?
- With what probability and confidence?
- Which contributors support or oppose it?

Forecast contributions are sparse probability blobs, not exact price predictions. Each contribution references an `AnalysisResult` ID and has horizon, price zone, probability, confidence, weight, decay, evidence refs and dependency group.

## Universal analyzer path

Analyzers may produce arbitrary module-specific payloads, but NOVA only reasons over standardized outputs:

- `AnalysisResult`: analyzer passport, payload, parameters used and input lineage.
- `ForecastContribution`: future price-time zone contribution.
- `StateContribution`: trust/regime/risk/data-quality contribution.

This allows future analyzers to add new data without changing Matrix internals.

## StateMatrix

Answers:

- Is the forecast trustworthy now?
- Is volatility stable or expanding?
- Are timeframes conflicting?
- Is liquidity persistent or spoof-like?
- Is data quality good enough?

## Important separation

- `probability`: chance of scenario/zone.
- `confidence`: trust in that estimate.

Example: UP probability may be 0.70, but confidence only 0.40 if data quality is weak.

## Synthetic TF caution

Synthetic 10m/15m/30m/1h built from 5m are not independent votes. They share `dependency_group = ohlcv_resampled` and must be weighted accordingly.

## Orderbook role

Orderbook is a short-lived liquidity/SR contributor. It is rate-limited and called on demand or no more often than policy allows.

## Lineage rule

All ForecastMatrix zones store contributor IDs. Contributions reference `analysis_result_id`. TradePlans reference matrix IDs. Outcomes reference TradePlan or Scenario IDs. Autotuner learns by walking this lineage backward.
