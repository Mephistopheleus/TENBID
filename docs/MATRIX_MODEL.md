# Matrix Model

## Purpose

The matrix models future price zones over time. It is not a direct trading decision.

NOVA Matrix is a **sparse evidence field**, not a buy/sell signal table and not a dense global grid. Empty price-time regions stay empty until evidence creates a local field there.

Hard terminology rule: nothing in Data, Analyzers or Matrix "votes" for a trade. These layers produce evidence, context, constraints, zones, conflicts, quality, uncertainty and lineage. Trade decisions belong only to the DecisionEngine / TradeCalculator / RiskManager / SafetyKernel path.

## ForecastMatrix

Answers:

- What price zone can be reached?
- Over which horizon?
- With what probability and confidence?
- Which contributors support or oppose it?

Forecast contributions are sparse field seeds, not exact price predictions. Each contribution references an `AnalysisResult` ID and can reference source cards. It has horizon, price zone, probability, confidence, weight, evidence refs, dependency group and evidence-flow metadata.

## Sparse evidence field

Forecast contributions create **islands of meaning**:

- `CORE`: the area explicitly described by the evidence.
- `HALO`: uncertainty around the core; weaker than the core and bounded by evidence.
- `BRIDGE`: a supported connection between nearby compatible islands.
- `TENSION`: a conflict area between nearby incompatible fields.

There is no global blur. The matrix must never invent probability in void regions just to make a complete heatmap.

The matrix must never flatten cards, timeframes or analyzers into `+1 long / -1 short` counters. A conflict between timeframes is a context/tension object, not arithmetic voting.

Nearby compatible fields may form a bridge when their price, horizon, direction and phenomenon are compatible. Nearby incompatible fields form tension, not an averaged forecast.

Current primary Matrix Core groups only overlapping compatible raw primary contributions: same scenario, phenomenon, field shape and close horizon. The grouped zone keeps the common overlap as `CORE` and stores the wider union as `HALO`; empty space outside contributed ranges remains empty.

Overlapping incompatible primary fields create `TENSION` zones with recheck metadata. Tension zones are context/attention objects, not trade decisions and not independent confirmation.

## CardDeck and no-echo rule

NOVA uses typed evidence cards to avoid self-confirming statistics:

- `DATA`
- `ANALYSIS`
- `FORECAST`
- `STATE`
- `MATRIX_ZONE`
- `VALIDATION`
- `REVISION`
- `RECHECK_REQUEST`
- `OUTCOME`
- `TUNING`

Every card has:

- `stage`: `RAW`, `MATRIX_BUILD`, `VALIDATION`, `REVISION`, `RECHECK`, `OUTCOME`, `TUNING`.
- `tier`: `PRIMARY`, `META`, `DERIVED`.
- `feedback_depth`.
- parent card IDs and optional input matrix ID.
- explicit influence rights.

Only raw primary cards/contributions with `feedback_depth = 0` may seed the primary forecast field.

Matrix-assisted validation or revision cards may update zone metadata, trust, conflict or recheck requests, but they do not become independent primary evidence for the same matrix.

Hard rule: **a primary matrix must not believe its own reflection within the same cycle**.

Cross-validated results are still part of the matrix system. They live in a validation/reconciliation layer: useful for DecisionEngine and assisted accuracy, but separated from raw primary statistics.

## Universal analyzer path

Analyzers may produce arbitrary module-specific payloads, but NOVA only reasons over standardized outputs:

- `AnalysisResult`: analyzer passport, payload, parameters used and input lineage.
- `EvidenceCard`: typed card with stage, tier, parents, feedback depth and influence rights.
- `ForecastContribution`: future price-time zone contribution.
- `StateContribution`: trust/regime/risk/data-quality contribution.

This allows future analyzers to add new data without changing Matrix internals.

Runtime analyzers receive the refreshed `MarketSnapshot` object plus lineage IDs through `AnalyzerContext`. They must not call Binance directly and must not output trade instructions.

Analyzers may build whole decks, not just one forecast. A deck can contain raw evidence, uncertainty notes, validation cards, revision cards, invalidation context and recheck requests. The matrix reads those cards according to their type and rights; it does not flatten the deck into one score.

## StateMatrix

Answers:

- Is the forecast trustworthy now?
- Is volatility stable or expanding?
- Are timeframes conflicting?
- Is liquidity persistent or spoof-like?
- Is data quality good enough?

Runtime v0 builds `StateMatrix` after the primary matrix. It summarizes data quality, matrix tension/recheck reasons and orderbook availability from the current `MarketSnapshot`. This is a trust/context layer only; it does not choose a market action.

## Important separation

- `probability`: chance of scenario/zone.
- `confidence`: trust in that estimate.
- `agreement_score`: compatibility of evidence around a zone.
- `conflict_score`: tension around a zone.
- `importance_score`: how much attention/recheck the zone deserves.

Example: UP probability may be 0.70, but confidence only 0.40 if data quality is weak.

## Validity and recheck

Strong zones should not merely fade on a timer. Time can make evidence stale, but in a dynamic market validity is also changed by:

- price entering/leaving core or halo;
- invalidation levels;
- volatility regime shift;
- liquidity change;
- new conflict/tension;
- missing data refresh.

High-importance zones can request recheck through `RECHECK_REQUEST` cards. The matrix does not run analyzers itself; it marks where attention is needed for the supervisor/scheduler.

## Synthetic TF caution

Synthetic 10m/15m/30m/1h built from 5m are scale/context layers, not independent trade evidence and not votes. They share `dependency_group = ohlcv_resampled` and must be interpreted through lineage and role.

Native higher-timeframe candles from the same market are useful for reconciliation, quality checks and corroboration, but they are still same-market aggregates. They must not be treated as fully independent confirmations merely because they were downloaded as native Binance intervals.

## Multi-scale topology

Future NOVA matrix layers may model scale as an axis, not as stepped timeframe rows:

```text
time x price x scale
```

This must remain sparse. The goal is not a dense 3D heatmap; the goal is typed cross-scale relations between evidence-backed zones:

- `CONTINUITY`: lower-scale structure continues higher-scale context.
- `TENSION`: lower-scale structure moves into higher-scale risk or conflict.
- `FRACTURE`: lower-scale structure starts breaking a higher-scale boundary.
- `COMPRESSION`: multiple scales converge in a narrow price-time area.
- `CONTAINMENT`: a local zone sits inside a larger context zone.
- `DIVERGENCE`: scales describe incompatible phenomena.

These relations produce context, constraints, recheck needs and ambiguity flags. They do not produce trade decisions.

## Multi-field topology

Price-time is the base matrix because TradePlans ultimately need price, time, risk, costs and invalidation. Other analyzers may produce field-like context only when the data has natural geometry:

- volume/value distribution fields;
- short-lived liquidity/orderbook fields;
- fractal/structure fields;
- trend/regime state fields;
- derivatives pressure fields;
- news/event decay fields.

NOVA must not create a dense surface for every analyzer by default. Non-geometric analyzers return cards, state contributions or constraints. Field layers interact through typed relations and lineage, not voting or flat score aggregation.

## StateSnapshot learning context

StateSnapshot records the runtime conditions around analysis, matrix and decision stages. It is training context, not an outcome label and not primary evidence.

Valid uses:

- explain when evidence worked or failed;
- tune conditional thresholds, decay and penalties;
- preserve data quality, liquidity, volatility, scale and conflict context at decision time;
- protect Shadow and Autotuner from hindsight leakage.

Invalid uses:

- merging state context into raw primary evidence accuracy;
- recomputing past state after outcome and treating it as known at decision time;
- turning state into a trade signal.

## Orderbook role

Orderbook is a short-lived liquidity/SR contributor. It is rate-limited and called on demand or no more often than policy allows.

## Lineage rule

All ForecastMatrix zones store contributor IDs. Contributions reference `analysis_result_id`. TradePlans reference matrix IDs. Outcomes reference TradePlan or Scenario IDs. Autotuner learns by walking this lineage backward.

Primary statistics must be computed from raw primary evidence only. Assisted/revised evidence is tracked separately so Autotuner can compare raw accuracy and matrix-assisted accuracy without echo pollution.

Current runtime implementation builds a sparse primary matrix from raw primary contributions. It groups compatible overlapping field seeds, emits tension metadata for incompatible overlaps, preserves empty space, logs lineage, and remains upstream of any future DecisionEngine / TradeCalculator / RiskManager path.
