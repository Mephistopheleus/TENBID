# NOVA Canon

## Purpose

The NOVA Canon is the fixed meaning boundary of the project: principle, logic, purpose and unique approach. It is not just style, architecture or wording. If a change breaks the Canon, the system stops being NOVA even if the code still runs.

NOVA is a trading system striving toward an ideal: it uses a unique structure and approach to build a full analysis and forecast of how the market situation may move.

## Core statement

NOVA does not search for a signal. NOVA builds the picture.

NOVA must not become another classic trading bot. It must not flatten the market into buy/sell/stop commands, module votes or generic signal arithmetic.

## Donor rule

The donor code is an archaeological layer, not an architecture template.

NOVA may extract from donors:

- what a module observed;
- which features it calculated;
- which zones, states, conflicts or pressures it detected;
- which input data it required;
- which result could still be useful as perception.

NOVA must not import from donors:

- old trade-decision mechanics;
- signal arithmetic;
- flat voting or flat weights;
- direct trade commands;
- analyzer-as-adviser behavior;
- classic bot terminology in Data, Analyzers or Matrix.

## Analyzer rule

An analyzer does not decide. An analyzer observes a phenomenon.

Each recovered analyzer must become an organ of perception. It may produce evidence, context, constraints, zones, uncertainty, conflicts, quality notes, state contributions or recheck requests. It must not issue trade instructions.

Examples:

- Old: strong volume level means buy or sell.
- NOVA: there is a volume concentration zone, a low-volume void, an acceptance/rejection area, a quality estimate, source lineage and expected lifetime.

- Old: orderbook wall means a signal.
- NOVA: there is a short-lived liquidity zone, thin or dense book state, increased slippage risk and a recheck need after a bounded interval.

- Old: derivatives pressure means a directional signal.
- NOVA: funding, open interest and positioning create external pressure, uncertainty or conflict with price structure.

## Matrix rule

The Matrix does not vote. It stores a sparse field of evidence-backed areas, contexts and tensions.

The Matrix may model:

- price-time zones;
- local fields and halos;
- bridges between compatible evidence;
- tensions between incompatible evidence;
- state and trust context.

The Matrix must not create a dense global heatmap only to fill empty space. Empty regions remain empty until evidence creates meaning there.

## State rule

State is not an outcome label.

`StateSnapshot` records the context of a moment: data quality, volatility, liquidity, conflicts, runtime phase and trust conditions. It is learning context, not primary evidence and not a trade signal.

`StateMatrix` answers whether the current market state allows trusting the forecast context. It does not choose a market action.

## Shadow and Laboratory rule

Shadow checks forbidden paths, alternatives and counterfactuals. It is not a substitute for TESTNET execution.

Laboratory checks what NOVA may be overtrusting or undertrusting. It exists to investigate errors and blind spots, not to bypass runtime safety.

## Autotuner rule

Autotuner tunes parameters inside the Canon. It must not rewrite the Canon.

Autotuner may adapt thresholds, decay, confidence handling, parameter profiles and conditional behavior when lineage and evidence support that change. It must not change owner-controlled boundaries, secrets, mode selection or the system's meaning model.

## Confidence and trust rule

Analyzer probability is the analyzer's own mathematical forecast of its observation. It is not data quality and not trade permission.

Autotuner trust points are separate from analyzer probability. They start at the minimum seed value and change only from traceable shadow, laboratory or real outcome evidence.

Data quality is only a gate for whether analysis may run. It must not be converted into trade confidence.

The canonical confidence flow is:

- per analyzer: `effective_confidence = average(analyzer_probability, autotuner_trust_points)`;
- for the deal: `deal_confidence = average(all effective_confidence values)`.

These values must not be summed or multiplied into a fake certainty number.

Until the minimum shadow / traceable outcome sample count is reached, normal executor approval is forbidden. Only explicit shadow, laboratory or owner-approved TESTNET probe paths may proceed.

## Safety and risk rule

`SafetyKernel` stores non-negotiable owner boundaries.

`RiskManager`, `TradeCalculator` and future decision components may calculate resource admissibility, cost, capacity and invalidation boundaries inside those limits. They do not own LIVE access.

LIVE remains owner-controlled. The owner personally switches mode and keys only after successful TESTNET evidence.

## Lineage rule

Every meaningful result must preserve lineage:

- data source;
- source snapshot;
- analyzer;
- parameters used;
- evidence card;
- matrix area or state contribution;
- state snapshot;
- trade plan or scenario;
- outcome.

If lineage is missing, the result cannot become trusted learning material for NOVA.

## Recovery workflow

Every donor module must pass this path before entering NOVA:

1. Extract the phenomenon.
2. Identify its role in NOVA.
3. Remove old decision mechanics.
4. Wrap the useful perception in NOVA contracts.
5. Preserve lineage.
6. Mark uncertainty and recheck needs explicitly.

The right question is not "what trade did this donor module want?"

The right question is "what part of the market did this donor module perceive, and how can NOVA represent that perception without breaking the Canon?"

## Canon checks

Use these phrases as hard review checks:

- this contradicts the NOVA Canon;
- this follows the NOVA Canon;
- this analyzer must be adapted through the NOVA Canon;
- this donor logic violates the NOVA Canon.
