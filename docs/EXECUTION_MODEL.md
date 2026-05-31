# Execution Model

## Executor naming

Use `ExchangeExecutor` / `BinanceFuturesConnector`, not `TestnetExecutor`.

The same execution pipeline should later work with LIVE keys, but current active mode is TESTNET and LIVE is locked.

## Config

`config/secrets.ini` contains:

- active trading mode
- TESTNET keyset
- LIVE keyset, initially empty

Autotuner must not modify this file.

## Pre-trade honesty

Before execution, `TradePlan` must include estimated:

- commission
- spread
- slippage
- total cost
- breakeven move
- net expected edge

Small gross moves that do not cover costs are rejected before execution.

## Safety vs dynamic risk

SafetyKernel is not the place for a fixed maximum number of simultaneous positions. Capacity is calculated dynamically by RiskManager/Autotuner from planned size, remaining balance, drawdown, risk budget and current context quality.

Independent opportunities should be evaluated independently; one candidate does not mechanically invalidate another just because it exists. Any shared constraint must come from actual balance/risk limits, not from a fixed hard-coded position count.
