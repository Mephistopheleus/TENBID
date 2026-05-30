# Analyzers placeholder

Analyzers are intentionally excluded from the first NOVA skeleton.

Later each analyzer must:

- read local snapshots/caches, not Binance directly;
- emit traceable `AnalysisResult` IDs;
- emit `ForecastContribution` / state contributions;
- declare dependency groups so synthetic TF is not counted as independent evidence.

