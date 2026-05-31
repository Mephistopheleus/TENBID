# NOVA Philosophy

## One sentence

NOVA is an adaptive trading system where every market decision is a tagged experiment, every parameter has lineage, and every outcome becomes evidence for the Autotuner.

## Foundations

### 1. Autotuner is the control loop

Autotuner is not an afterthought. It is the system's adaptive layer. It must adjust active profiles through `ParameterStore` / `ProfileManager`, not by scattered hardcoded constants.

Autotuner may tune working parameters such as thresholds, weights, SL/TP ranges, matrix dominance, trailing behavior and data access limits. It must not change secrets, trading mode, safety locks or immutable risk boundaries.

### 2. Matrix is the probabilistic market model

The matrix is not a trade-decision switch. It is a price-time probability field built from traceable contributions.

Data, analyzers, timeframes and matrix cards do not vote and do not issue trade decisions. They produce evidence, context, constraints, zones, conflicts, quality, uncertainty and lineage. Trade construction belongs to the DecisionEngine / TradeCalculator / RiskManager path.

The model has two sides:

- `ForecastMatrix`: where price may go, over what horizon, and with what probability.
- `StateMatrix`: whether the current market state allows trusting that forecast.

### 3. Logs are memory

NOVA must log all meaningful facts as events: data snapshots, matrix builds, trade plans, shadow outcomes, lab experiments, parameter changes and executor results.

If it was not logged, it does not exist for Autotuner.

### 4. TESTNET is the working reality

NOVA is not built around dry-run as the source of truth. Binance Futures TESTNET is the live-like execution path until a much later LIVE stage.

Shadow exists for alternatives, forbidden trades and laboratory scenarios. It does not replace testnet execution.

### 5. Costs are pre-trade facts

Commission, spread, slippage and minimum breakeven movement must be estimated before a TradePlan is accepted. Outcome must record planned vs actual costs; it must not retroactively "damage" a trade and confuse Autotuner.

### 6. Dynamics, not only snapshots

The system should learn from market episodes, not only isolated snapshots. A trade is part of a video: matrix slope, confidence trend, volatility expansion, liquidity persistence, MFE/MAE and state conflict changes.
