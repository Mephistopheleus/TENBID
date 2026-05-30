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

