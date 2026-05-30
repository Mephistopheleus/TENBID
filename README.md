# NOVA

NOVA is a clean-room rebuild of TENBID.

This branch intentionally starts empty: no old runtime is copied wholesale. The old backups are evidence sources only. NOVA will be filled by contracts, measured behavior, and proven fragments.

## Core idea

NOVA is not an indicator bot. It is an adaptive trading system with memory:

- **Autotuner** is the control loop for parameters and trust.
- **ForecastMatrix / StateMatrix** are the probabilistic market model.
- **EventLog / Episodes** are the system memory and market "video".
- **Shadow / ScenarioEvaluator** is the single engine for alternative outcomes.
- **Laboratory** generates hypotheses; it does not calculate PnL itself.
- **ExchangeExecutor** is real Binance Futures execution, currently TESTNET-only.

## Current phase

Architecture skeleton only. No analyzers are implemented yet.

Analyzers must later speak NOVA contracts:

- `AnalysisResult`
- `EvidenceCard` / `CardDeck`
- `ForecastContribution`
- `StateContribution`

Matrix input is a typed evidence flow, not a flat signal vote. Raw primary cards may seed sparse forecast fields; validation, revision and recheck cards update metadata and attention without polluting primary statistics.

## Safety and mode

NOVA is designed with TESTNET and LIVE key sections, but the active mode is TESTNET. LIVE execution remains locked until explicitly designed and reviewed later.
