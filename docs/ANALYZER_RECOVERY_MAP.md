# Analyzer Recovery Map

## Purpose

This map controls recovery of donor analyzers into NOVA without importing the old bot logic. Donor files are evidence sources only. Each analyzer must be reduced to the phenomenon it perceived, then rebuilt through NOVA contracts.

Primary Canon reference: `docs/NOVA_CANON.md`.

## Recovery contract

For every donor analyzer, record:

- donor file;
- phenomenon observed;
- required input data;
- old output or behavior to reject;
- useful perception to preserve;
- NOVA output contract;
- missing Data-layer needs;
- Canon risk;
- priority.

Allowed NOVA outputs:

- `AnalysisResult` for analyzer payload and lineage;
- `EvidenceCard` for typed evidence and recheck requests;
- `ForecastContribution` for sparse price-time areas;
- `StateContribution` for trust, regime, liquidity, uncertainty or data-quality context.

Forbidden recovered outputs:

- buy/sell/stop commands;
- direct execution advice;
- flat analyzer votes;
- signal counters;
- hidden side effects or direct exchange calls from analyzers;
- unlineaged confidence.

## Current NOVA baseline

Already present in NOVA:

- `nova/analyzers/market_structure.py` as the first MarketSnapshot-backed structure analyzer;
- `AnalyzerContext`, `AnalysisPackage`, `AnalysisResult`, `EvidenceCard`, `ForecastContribution`, `StateContribution` contracts;
- `ForecastMatrix` sparse field;
- `StateMatrix` trust/context layer;
- `MarketSnapshot` and Data-layer lineage foundation.

## Donor analyzer map

| Priority | Donor file | Phenomenon | Inputs needed | Reject from donor | Preserve for NOVA | NOVA output | Data-layer needs | Canon risk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P1 | `TENBID/analyzers/volume_profile.py` | Volume distribution, value concentration, acceptance/rejection areas, low-volume voids | OHLCV candles, volume buckets, symbol precision, timeframe lineage | Directional trade instruction from level strength | Volume nodes, POC/value-like areas, imbalances, profile shape, quality/lifetime | `AnalysisResult`, `EvidenceCard`, optional `ForecastContribution` for volume/value zones, `StateContribution` for acceptance/void context | Confirm candle volume quality and bucket metadata in snapshot lineage | High: can easily become support/resistance signal logic |
| P1 | `TENBID/analyzers/orderbook_analysis.py` | Short-lived liquidity structure, book density/thinness, walls, slippage risk | Orderbook snapshot, timestamp, depth limit, refresh age, spread | Wall = signal, static support/resistance decision | Liquidity zones, imbalance, spread/slippage risk, recheck timing | `AnalysisResult`, `EvidenceCard`, `StateContribution`, `RECHECK_REQUEST`; optional short-lived `ForecastContribution` only when price-zone geometry is explicit | Orderbook cache already exists; add freshness and lifetime metadata where needed | High: orderbook is noisy and short-lived |
| P1 | `TENBID/analyzers/derivatives_analyzer.py` | Derivatives pressure from funding/OI/positioning | Funding, open interest, long/short ratio, timestamped source refs | Overheated longs/shorts = directional signal | External pressure, leverage crowding, uncertainty, conflict with price structure | `AnalysisResult`, `EvidenceCard`, `StateContribution`; optional conflict metadata for Matrix | Need DerivativesSnapshot population from exchange/public data | High: classic contrarian signal temptation |
| P1 | `TENBID/analyzers/multi_tf_context.py` | Cross-scale context and timeframe relations | Native and synthetic candle series, timeframe roles, dependency groups | Timeframe vote aggregation | Continuity, containment, tension, fracture, compression, divergence | `AnalysisResult`, `EvidenceCard`, `ForecastContribution` relation metadata, `StateContribution` for scale conflict | Timeframe role metadata and native/synthetic lineage already partly exists | High: must avoid treating resampled TFs as independent votes |
| P2 | `TENBID/analyzers/fractal_analysis.py` | Local structure, swing geometry, nested scale behavior | OHLCV candles across relevant scales | Pattern implies direct entry/exit | Fractal boundaries, breaks, compression/expansion, structural uncertainty | `AnalysisResult`, `EvidenceCard`, possible `ForecastContribution` zones and invalidation context | Need stable swing/structure primitives if not present | Medium-high: can become pattern signal logic |
| P2 | `TENBID/analyzers/pattern_recognition.py` | Recognized market shapes and local formations | OHLCV candles, volatility context, timeframe role | Pattern name = trade setup | Shape context, quality, failure conditions, interaction with zones | `AnalysisResult`, `EvidenceCard`, optional `ForecastContribution` only with bounded zone/horizon | Need pattern payload schema and quality model | High: pattern labels often smuggle old trade rules |
| P2 | `TENBID/analyzers/market_regime.py` | Regime, volatility/trend/range state | OHLCV, volatility measures, trend/structure metrics | Regime chooses trade side | Trust context, volatility expansion/compression, market state constraints | `AnalysisResult`, `StateContribution`, `EvidenceCard` | Volatility/regime fields in StateSnapshot/StateMatrix may need expansion | Medium |
| P2 | `TENBID/analyzers/btc_correlation.py` | BTC/primary-symbol relation and external market pressure | Primary symbol candles, BTC candles, synchronized timestamps | Correlation = signal | Correlation strength, divergence, systemic pressure, risk context | `AnalysisResult`, `EvidenceCard`, `StateContribution` | Need multi-symbol MarketSnapshot support | Medium |
| P3 | `TENBID/analyzers/news_sentiment.py` | News/event pressure and decay | News items, source, timestamp, relevance, decay horizon | Sentiment = buy/sell decision | Event pressure, relevance, uncertainty, expected decay/lifetime | `AnalysisResult`, `EvidenceCard`, `StateContribution`; possible event-decay field later | NewsBatch source and reliability scoring need implementation | High: external text is noisy and can overfit |
| P3 | `TENBID/analyzers/market_analyzer.py` | Aggregated legacy market summary | Mixed donor analysis outputs | Aggregation, voting, summary decision | Only extract any unique metrics not already covered elsewhere | Case-by-case; usually no direct port | Depends on extracted sub-phenomena | Very high: likely old orchestration logic |
| P3 | `TENBID/analyzers/data_manager.py` | Legacy data acquisition/helper behavior | Exchange/public data inputs | Analyzer-layer direct API access | Any useful data normalization or source assumptions | Data-layer service only, not analyzer | Must remain outside analyzers | High: violates no analyzer direct API access |
| P3 | `TENBID/analyzers/synthetic_timeframes.py` | Resampled timeframe construction | Base candle series | Synthetic TF as independent confirmation | Resampling mechanics and dependency lineage | Data-layer utility only; analysis via timeframe role metadata | Synthetic builder already exists in NOVA | Medium |

## Non-analyzer donor modules to recover later

These are not analyzers, but they contain useful mechanisms that must also be filtered through the Canon.

| Priority | Donor file | Useful phenomenon/mechanism | Reject | NOVA target |
| --- | --- | --- | --- | --- |
| P2 | `TENBID/core/autotuner.py` | Parameter learning, context/outcome history, lab insight integration | Rewriting Canon, opaque weight changes, signal-weight tuning | Autotuner recommendations over registered parameters with lineage |
| P2 | `TENBID/core/trade_calculator.py` | Cost/risk-aware trade construction | Direction from analyzer signals, fixed stop framing | Future DecisionEngine/TradeCalculator using Matrix, costs and invalidation boundaries |
| P2 | `TENBID/core/risk_manager.py` | Resource admissibility and policy checks | Owning immutable safety or LIVE switch | RiskManager inside SafetyKernel boundaries |
| P3 | `TENBID/trading/position_sizer.py` | Dynamic capacity sizing | Confidence-as-command sizing | Risk capacity helper fed by trusted context only |
| P3 | `TENBID/trading/smart_trailing.py` | Adaptive position management after entry | Classic trailing-stop as analyzer output | Future execution/position management, not Data/Analyzer/Matrix |
| P3 | `TENBID/shadow/shadow_calculator.py` | Forbidden-path and alternative scenario analysis | Using shadow to bypass real TESTNET path | ShadowEngine scenario contracts and outcome lineage |

## Per-analyzer recovery steps

1. Read donor file and list all data inputs.
2. List every output and separate perception from decision mechanics.
3. Remove old trade commands, votes, signals and direct exchange access.
4. Define the NOVA phenomenon name.
5. Define payload schema and lineage fields.
6. Decide whether output belongs to `ForecastContribution`, `StateContribution`, `EvidenceCard`, or only `AnalysisResult`.
7. Add Data-layer fields first if the analyzer needs missing data.
8. Add tests or smoke validation before runtime registration.
9. Register only after the analyzer preserves the Canon.

## First recommended recovery order

1. Volume profile: high value as a field-like zone source.
2. Orderbook analysis: already supported by the new cache policy, but must stay short-lived and rechecked.
3. Derivatives pressure: important state/external-risk context once data exists.
4. Multi-timeframe context: needed for scale topology, but must avoid votes.
5. Fractal/structure and pattern modules: useful after stricter zone contracts are stable.

