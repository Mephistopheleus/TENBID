# Matrix Model

## Purpose

The matrix models future price zones over time. It is not a direct trading decision.

## ForecastMatrix

Answers:

- What price zone can be reached?
- Over which horizon?
- With what probability and confidence?
- Which contributors support or oppose it?

Forecast contributions are sparse probability blobs, not exact price predictions. Each contribution has source ID, horizon, price zone, probability, confidence, weight, decay and dependency group.

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

