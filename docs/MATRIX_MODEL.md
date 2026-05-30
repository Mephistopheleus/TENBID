# Matrix Model

## Purpose

The matrix models future price zones over time. It is not a direct trading decision.

NOVA Matrix is a **sparse evidence field**, not a buy/sell signal table and not a dense global grid. Empty price-time regions stay empty until evidence creates a local field there.

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

Nearby compatible fields may form a bridge when their price, horizon, direction and phenomenon are compatible. Nearby incompatible fields form tension, not an averaged forecast.

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

## Universal analyzer path

Analyzers may produce arbitrary module-specific payloads, but NOVA only reasons over standardized outputs:

- `AnalysisResult`: analyzer passport, payload, parameters used and input lineage.
- `EvidenceCard`: typed card with stage, tier, parents, feedback depth and influence rights.
- `ForecastContribution`: future price-time zone contribution.
- `StateContribution`: trust/regime/risk/data-quality contribution.

This allows future analyzers to add new data without changing Matrix internals.

Analyzers may build whole decks, not just one forecast. A deck can contain raw evidence, uncertainty notes, validation cards, revision cards, invalidation context and recheck requests. The matrix reads those cards according to their type and rights; it does not flatten the deck into one score.

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

Synthetic 10m/15m/30m/1h built from 5m are not independent votes. They share `dependency_group = ohlcv_resampled` and must be weighted accordingly.

## Orderbook role

Orderbook is a short-lived liquidity/SR contributor. It is rate-limited and called on demand or no more often than policy allows.

## Lineage rule

All ForecastMatrix zones store contributor IDs. Contributions reference `analysis_result_id`. TradePlans reference matrix IDs. Outcomes reference TradePlan or Scenario IDs. Autotuner learns by walking this lineage backward.

Primary statistics must be computed from raw primary evidence only. Assisted/revised evidence is tracked separately so Autotuner can compare raw accuracy and matrix-assisted accuracy without echo pollution.
