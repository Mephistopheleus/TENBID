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

