# NOVA Core Freeze and Build Plan

## Purpose

This document freezes the current NOVA skeleton and defines the build order for a working TESTNET system.

The goal is to stop endless re-unification. The project already has enough typed input/output structure to protect the architecture. New analyzers and data sources must connect to this skeleton instead of forcing a new skeleton each time.

Canon reference: `docs/NOVA_CANON.md`.

Context checkpoint: `docs/NOVA_CONTEXT_CHECKPOINT_2026-06-01.md`.

## Core freeze statement

The following contracts are treated as stable core skeleton unless a critical defect is found:

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
- `ScenarioRequest`
- `ScenarioOutcome`
- runtime config and parameter profiles

Core freeze does not mean the code is complete. It means the ownership and data boundaries are stable enough to build the working system.

## Rules for adding new data

New market information must enter through the Data layer.

Allowed paths:

1. Add a typed optional block to `MarketSnapshot` when the data is broadly useful.
2. Add a dedicated Data-layer service/cache if the source has refresh, quality or rate-limit policy.
3. Store analyzer-specific detail inside `AnalysisResult.payload` when it does not belong in the global snapshot.
4. Preserve source lineage and data quality.

Forbidden paths:

- analyzer direct exchange/API calls;
- changing Matrix contracts for one analyzer;
- adding untyped global dictionaries as hidden coupling;
- turning new data into direct trade commands.

Canon comment:

```text
New data expands perception; it must not rewrite NOVA's skeleton.
```

## Rules for adding new analyzers

New analyzers are organs of perception.

They may output:

- `AnalysisResult`
- `EvidenceCard`
- `ForecastContribution`
- `StateContribution`
- recheck requests through evidence cards

They must not output:

- buy/sell/stop commands;
- execution instructions;
- votes;
- signal counters;
- direct risk decisions.

Canon comment:

```text
Analyzers observe phenomena. They do not decide.
```

## Layer roles

### Data layer

Owns external data access, refresh policy, quality, lineage and caching.

Data layer answers:

- what data was available;
- where it came from;
- when it was refreshed;
- whether it is usable;
- what gaps or quality limits exist.

### Analyzers

Observe market phenomena from `AnalyzerContext`.

They do not call exchanges directly and do not make trade decisions.

### ForecastMatrix

Aggregates analyzer outputs into sparse market picture fields.

It may absorb, group and approximate compatible evidence-backed regions, while preserving incompatible structure instead of flattening it.

It does not decide.

### StateMatrix

Aggregates trust and context around the current market picture.

It may describe freshness, quality, instability, liquidity context, conflict and recheck need.

It does not decide, open, forbid or size trades.

### ScenarioBuilder

Preferred name for the old "decision layer" idea.

It builds a computable `ScenarioCandidate` only when the current Matrix/State picture has enough structure.

It returns HOLD/no-scenario when the picture is insufficient.

It is not a signal helper.

### TradeCalculator

Calculates a `TradePlan` from a scenario candidate.

It computes the form of a possible trade: entry/execution area, invalidation boundary, size, costs, slippage assumptions, minimum breakeven movement and initial management plan.

It does not place orders.

### RiskManager

Checks whether a `TradePlan` is admissible before opening.

After opening, it monitors each position's own assumptions and danger signs separately.

It may request reduce/close/breakeven escape actions through the position-management path.

It does not own LIVE access and does not overwrite `SafetyKernel`.

### SafetyKernel

Stores owner-level non-negotiable boundaries.

LIVE unlock is not a development task.

### PositionManager / PositionController

Tracks every opened position and its original scenario lineage.

It coordinates ongoing management, risk checks and adaptive trailing decisions.

### AdaptiveTrailingPolicy

Calculates adaptive protective boundaries and breakeven/trailing behavior.

Autotuner may tune its parameters, but the policy remains inside the owner safety boundaries and the original trade scenario context.

### Executor

Physical exchange edge for TESTNET first.

It places, cancels, modifies and closes orders, and reads status.

It does not contain the main risk/trailing intelligence.

### OutcomeRecorder

Records planned vs actual behavior with lineage:

- scenario;
- trade plan;
- risk approval/rejection;
- orders;
- fills;
- costs;
- slippage;
- position management actions;
- final outcome.

### Shadow, Laboratory and Autotuner

They learn from traceable outcomes.

Shadow checks alternatives and forbidden paths.

Laboratory checks overtrusted and undertrusted logic.

Autotuner tunes registered parameters inside the Canon.

## Build sequence

### Stage 1 — Freeze and checkpoint

Status: current stage.

Deliverables:

- `docs/NOVA_CANON.md`
- `docs/ANALYZER_RECOVERY_MAP.md`
- `docs/NOVA_CONTEXT_CHECKPOINT_2026-06-01.md`
- `docs/NOVA_CORE_FREEZE_AND_BUILD_PLAN.md`

Done when these documents are committed and pushed.

### Stage 2 — ScenarioBuilder skeleton

Create a small, explicit scenario-building layer.

Inputs:

- `ForecastMatrix`
- `StateMatrix`
- `MarketSnapshot`
- runtime profile/config

Outputs:

- computable scenario candidate; or
- HOLD/no-scenario reason with lineage.

Canon comment:

```text
A scenario is a bounded hypothesis, not a signal.
```

### Stage 3 — TradeCalculator completion

Make `TradeCalculator` calculate a `TradePlan` from the scenario candidate.

Required calculations:

- execution/entry area;
- invalidation boundary;
- position size;
- commission/spread/slippage estimate;
- minimum breakeven movement;
- initial management plan.

Canon comment:

```text
TradeCalculator calculates form; it does not open trades.
```

### Stage 4 — RiskManager pre-trade gate

Implement dynamic pre-trade admissibility.

Inputs:

- `TradePlan`
- `StateMatrix`
- active positions/resource state;
- safety policy;
- runtime profile.

Outputs:

- approved;
- rejected;
- reduced;
- requires recheck.

Canon comment:

```text
RiskManager checks resource/context admissibility inside owner safety boundaries.
```

### Stage 5 — TESTNET Executor edge

Connect approved plans to TESTNET-only physical execution.

Required behavior:

- place order;
- cancel/modify where supported;
- close position;
- read order/position status;
- log all executor results.

Canon comment:

```text
Execution is physical action at the edge, not intelligence in the center.
```

### Stage 6 — PositionManager and AdaptiveTrailingPolicy

Add post-open position management.

Required behavior:

- track each position separately;
- keep original scenario and trade-plan lineage;
- calculate adaptive protective boundaries;
- detect breakeven escape opportunities;
- request executor actions through approved path.

Canon comment:

```text
Position management continues the scenario; it does not invent a new unlineaged trade.
```

### Stage 7 — OutcomeRecorder

Close the learning loop by recording planned vs actual behavior.

Required output:

- trade lifecycle events;
- costs and slippage;
- MFE/MAE if available;
- risk/trailing interventions;
- final outcome;
- full lineage.

Canon comment:

```text
Without lineage, an outcome cannot teach NOVA.
```

### Stage 8 — Autotuner / Shadow / Laboratory runtime integration

Only after executable outcomes exist, connect learning components to real traceable outcome flow.

Canon comment:

```text
Autotuner learns from outcomes; Shadow and Laboratory investigate alternatives and mistakes.
```

### Stage 9 — Add perception organs without changing the skeleton

Recover or create analyzers as NOVA-native modules:

- VolumeField;
- OrderbookLiquidity;
- DerivativesPressure;
- MultiScaleContext;
- FractalStructure;
- PatternShape;
- NewsEventPressure.

Canon comment:

```text
New analyzers expand sight, not authority.
```

## Stop condition for architecture expansion

Do not add another generic abstraction unless one of these is true:

1. A current stable contract cannot represent necessary lineage.
2. A safety boundary cannot be expressed without a new contract.
3. TESTNET execution/outcome logging cannot be made honest with existing contracts.

If none of these is true, continue building the executable loop instead of re-unifying.

## Next practical action after this checkpoint

After this document is committed and pushed, continue with Stage 2: `ScenarioBuilder` skeleton.

Before coding Stage 2:

1. Read `docs/NOVA_CANON.md`.
2. Read this file.
3. Inspect existing `TradePlan`, `ForecastMatrix`, `StateMatrix`, `CycleRunner` and runtime flow.
4. Propose a small scenario candidate contract.
5. Implement only after confirming it does not become a signal helper.

