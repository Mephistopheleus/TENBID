# Architecture

## High-level flow

```text
Binance WS / REST
  -> CandleCache / DataScheduler
  -> MarketSnapshot
  -> Analyzers later produce AnalysisResult + ForecastContribution
  -> Pre-matrix validation
  -> ForecastMatrix + StateMatrix
  -> DynamicsContext from MarketEpisode
  -> TradeCalculator + RiskManager
  -> TradePlan
  -> ExchangeExecutor or ShadowEngine
  -> Outcome
  -> EventLog / HistoryDB / EpisodeBuilder
  -> Laboratory / Autotuner
  -> ParameterProfile update
```

## Module responsibility

- `core`: IDs, events, config/profile access, safety, event log.
- `data`: Binance data access, candle cache, synthetic TF and reconciliation.
- `matrix`: forecast/state matrix contracts and aggregation.
- `decision`: trade plan and pre-trade calculation.
- `risk`: safety-bounded sizing and risk gates.
- `execution`: one exchange executor for TESTNET now and LIVE later.
- `shadow`: scenario evaluation and online shadow positions.
- `labs`: hypothesis generation and dispatch to scenario evaluator.
- `episodes`: market video / dynamics windows.
- `autotune`: evidence collection, recommendations and profile updates.
- `supervisor`: system liveness, reconnects, cycles and shutdown.

## Main.py rule

`main.py` must not become the trading brain. It starts `SystemSupervisor` and delegates.

Supervisor owns stability: reconnects, heartbeat, caches, gap recovery and graceful shutdown.

