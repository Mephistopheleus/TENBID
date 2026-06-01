# NOVA Context Checkpoint — 2026-06-01

This document is a recovery point for the dialogue and development state after the context-compression issue. It must be treated as project evidence, not as model memory.

## Why this checkpoint exists

During the dialogue, part of the earlier conversation was optimized away from active context. The missing part included the original formulation of the NOVA Canon and the agreement to preserve it in project documents.

The repository showed that the Canon had been discussed but not physically saved before the checkpoint. The issue was diagnosed through Git/project state rather than assumptions.

Current rule after any future context compression:

1. Do not continue from memory alone.
2. Read project documents first.
3. Check Git state.
4. Report uncertainty before acting.
5. Continue only after the next action is aligned with the NOVA Canon.

## Current verified Git state

Workspace:

```text
/workspaces/TENBID/temp-work/NOVA
```

Branch:

```text
TENBID/NOVA
```

Current pushed HEAD before this checkpoint:

```text
94feb34 Add NOVA canon and analyzer recovery map
```

That commit added:

- `docs/NOVA_CANON.md`
- `docs/ANALYZER_RECOVERY_MAP.md`

## Canon decisions fixed in the dialogue

NOVA is not another classic trading bot.

NOVA is a trading system striving toward an ideal: it uses a unique structure and approach to build a full analysis and forecast of how the market situation may move.

Core wording:

```text
NOVA does not search for a signal.
NOVA builds the picture.
```

The donor code is an archaeological layer, not an architecture template.

Donor modules may be used to recover:

- what they observed;
- which market phenomena they tried to perceive;
- which data they needed;
- which calculations were useful before old decision logic infected them.

Donor modules must not bring back:

- buy/sell/stop framing in Data, Analyzers or Matrix;
- voting analyzers;
- flat signal arithmetic;
- direct trade commands;
- old bot-like orchestration.

Analyzers are organs of perception, not decision-makers.

## Decision about analyzer recovery

We agreed not to port donor analyzers directly.

The safer approach is:

```text
donor = material for understanding the phenomenon
NOVA = new implementation of that phenomenon through NOVA contracts
```

Example: instead of adapting old `volume_profile.py` directly, NOVA should eventually create a native volume-field perception module if needed. Its purpose is not to produce a trade direction, but to perceive:

- volume concentration zones;
- acceptance/rejection areas;
- low-volume voids;
- center of recent volume gravity;
- profile width and quality;
- multi-scale volume relations where useful.

## Decision about v0/v1 wording

The user explicitly raised concern that `v0`, `v1`, `v2` could imply endless rewrites.

Accepted interpretation:

```text
v0 = final architectural form with minimal depth
v1 = more depth inside the same form, not a system rewrite
```

NOVA must not proceed by building disposable temporary modules that will later force full architectural replacement.

## Decision about core freeze

We agreed that the project has already unified enough of the core data and output contracts.

The next move is not another round of generic unification. The next move is to freeze the current skeleton and protect it from being broken by each newly recovered data source or analyzer.

Stable skeleton to preserve:

- `MarketSnapshot`
- `DataQualityReport`
- `AnalyzerContext`
- `AnalysisPackage`
- `AnalysisResult`
- `EvidenceCard`
- `ForecastContribution`
- `StateContribution`
- `ForecastMatrix`
- `StateMatrix`
- `TradePlan`
- `ScenarioRequest` / `ScenarioOutcome`
- runtime config and parameter profiles

New data types should not force a full architecture change. They must enter through the Data layer as typed optional data or analyzer-specific payload with lineage.

## Clarified layer roles

### ForecastMatrix

The matrix is a multidimensional aggregator of analyzer results with absorption and approximation behavior. It aggregates evidence into market picture fields.

It does not make decisions and does not search for trade signals.

It should not flatten incompatible evidence. If different data describes different areas or incompatible states, the matrix preserves that structure instead of averaging it into a fake consensus.

### StateMatrix

StateMatrix is not the RiskManager and not a judge that opens or forbids trades.

StateMatrix is a context/trust panel for the current market picture. It aggregates conditions such as:

- data freshness and gaps;
- data quality reports coming from Data layer;
- volatility/instability context;
- liquidity context;
- matrix tension/recheck needs;
- scale conflicts or uncertainty.

It does not decide whether to trade. It provides state context to ScenarioBuilder, RiskManager, PositionManager and later Autotuner.

### ScenarioBuilder

The phrase `Decision layer` was considered too dangerous because it can sound like a signal helper.

Preferred role/name:

```text
ScenarioBuilder
```

It does not look for tips or signals. It converts the current market picture into a computable scenario candidate only when the picture has enough structure.

If no computable scenario exists, it returns HOLD/no-scenario with lineage and reason.

### TradeCalculator

TradeCalculator calculates the form of a possible trade from a scenario candidate.

It may calculate:

- execution/entry area;
- invalidation boundary;
- size;
- costs;
- slippage assumptions;
- minimum breakeven movement;
- expected range;
- initial management plan.

It must not physically place orders.

### RiskManager

RiskManager is dynamic.

Before opening, it checks admissibility of a `TradePlan` against resources, state context, active positions and safety boundaries.

After opening, it tracks each position separately and detects whether that specific trade's assumptions are becoming dangerous.

It should support early defensive actions such as breakeven escape before hard invalidation when the context deteriorates.

### Executor

Executor is the physical exchange edge.

It opens, closes, modifies/cancels orders and checks order/position status.

Executor should not contain the main intelligence of trailing or risk. It should execute approved instructions reliably.

### PositionManager and AdaptiveTrailingPolicy

Adaptive trailing should not be hidden as ad-hoc logic inside Executor.

Preferred separation:

```text
PositionManager / PositionController
    uses AdaptiveTrailingPolicy
    consults RiskManager
    asks Executor to perform physical actions
```

Autotuner may tune trailing parameters, but must not directly control execution or rewrite the Canon.

### LIVE rule

LIVE remains owner-controlled. The owner personally switches mode and keys only after successful TESTNET evidence.

Development work must focus on TESTNET execution and outcome logging.

## Main strategic decision

Stop expanding generic architecture.

Freeze the core skeleton and start closing the executable loop:

```text
Data
  -> Analyzers
  -> ForecastMatrix
  -> StateMatrix
  -> ScenarioBuilder
  -> TradeCalculator
  -> RiskManager
  -> PositionManager / AdaptiveTrailingPolicy
  -> TESTNET Executor
  -> OutcomeRecorder
  -> Autotuner / Shadow / Laboratory learning
```

New analyzers should be added after or alongside this loop without changing the skeleton.

## Immediate next planned document

Create/follow:

```text
docs/NOVA_CORE_FREEZE_AND_BUILD_PLAN.md
```

Purpose:

- freeze stable contracts;
- define how new data/analyzers enter without breaking the skeleton;
- define the executable build order;
- keep Canon commentary attached to each stage.

## Morning recovery instruction

If continuing after sleep, reload or context compression:

1. Read `docs/NOVA_CANON.md`.
2. Read `docs/NOVA_CONTEXT_CHECKPOINT_2026-06-01.md`.
3. Read `docs/NOVA_CORE_FREEZE_AND_BUILD_PLAN.md`.
4. Run `git status --short --branch` in `/workspaces/TENBID/temp-work/NOVA`.
5. Continue with the next item in the build plan, not with remembered dialogue.

