# Analyzers

Analyzers observe market phenomena from local snapshots/caches and emit
traceable evidence. They do not decide trades and do not query Binance directly.

Each analyzer must:

- read local snapshots/caches, not Binance directly;
- emit traceable `AnalysisResult` IDs;
- emit `ForecastContribution` / state contributions;
- declare dependency groups so synthetic TF is not counted as independent evidence.
