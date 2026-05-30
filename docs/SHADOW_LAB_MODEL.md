# Shadow and Laboratory Model

## Single calculation engine

`ScenarioEvaluator` is the only engine that calculates alternative scenario outcomes.

It evaluates:

- HOLD shadow scenarios
- lab experiments
- matrix validation scenarios
- parameter sweeps
- alternative SL/TP/trailing variants

## ShadowEngine

Online component. Creates scenario requests from current HOLD or non-selected candidates.

## Laboratory

Laboratory does not calculate PnL. It studies episodes, generates hypotheses and sends `ScenarioRequest` to `ScenarioEvaluator`.

## Market video

Laboratory should learn from `MarketEpisode`, not only one snapshot. Episode includes pre-trade and in-trade dynamics: matrix slope, confidence trend, volatility, liquidity, MFE/MAE and exit pressure.

## Tags matter

Every outcome must be tagged by source:

- `REAL_EXECUTION`
- `HOLD_SHADOW`
- `LAB_EXPERIMENT`
- `MATRIX_VALIDATION`
- `PARAMETER_SWEEP`

Autotuner uses tags to decide which sources deserve trust.

