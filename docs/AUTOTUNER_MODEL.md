# Autotuner Model

## Role

Autotuner is the control loop that reads evidence and writes parameter recommendations.

It must not calculate scenario outcomes itself. It reads outcomes from real execution, shadow and laboratory experiments.

## Evidence sources

1. Real TESTNET outcomes from `ExchangeExecutor`.
2. Shadow outcomes from online forbidden/alternative scenarios.
3. Laboratory outcomes from experiments dispatched to `ScenarioEvaluator`.
4. Matrix prediction accuracy after price path resolution.
5. Cost model errors: planned vs actual spread/slippage/commission.

Autotuner must preserve the evidence tier when reading matrix history:

- raw primary evidence measures independent analyzer accuracy;
- validation/revision evidence measures matrix-assisted behavior;
- recheck cards measure attention/scheduler quality.

These streams must not be collapsed into one statistic, otherwise matrix feedback can look like independent confirmation.

## StateSnapshot rule

State snapshots are training context, not training labels.

Autotuner may use `StateSnapshot` rows to learn under which conditions evidence, matrices, TradePlans and outcomes worked or failed:

- data quality and freshness;
- volatility/regime state;
- liquidity state;
- scale tension or conflict;
- cross-field relations;
- recheck flags;
- snapshot stage and lineage.

Autotuner must not collapse state context into primary evidence accuracy or outcome labels. The learning streams remain separated:

```text
RAW evidence snapshot
StateSnapshot context_at_decision_time
Decision/TradePlan snapshot
Outcome snapshot
Autotune target
```

StateSnapshot must be immutable, timestamped, stage-separated and logged before the outcome is known. Recomputing past state after the outcome and treating it as if it was known at decision time is leakage and is forbidden.

## Output

`AutotuneRecommendation` with:

- target profile
- proposed parameter changes
- evidence IDs
- sample size
- confidence
- rollback condition

`ProfileManager` validates and applies recommendations atomically to `active_profile.json`.

## Rule

Autotuner changes active profile parameters, not secrets, keys, mode or safety locks.

## Parameter registry

New modules can add new tunable parameters if they register `ParameterSpec`:

- parameter name
- owner module
- type/default/bounds/step
- risk level
- autotune enabled flag

Analyzer `AnalysisResult` must include `parameters_used`. This lets Autotuner connect outcomes back to the exact parameter values that produced each contribution.

With this contract, Autotuner can tune future analyzer parameters without changing its core logic.

## No-echo learning rule

Matrix-assisted cards and contributions keep `input_matrix_id`, parent IDs and `feedback_depth`. Autotuner must treat `feedback_depth = 0` raw primary evidence separately from derived or meta evidence.

This lets NOVA improve through cross-validation without polluting primary matrix statistics with its own reflections.
