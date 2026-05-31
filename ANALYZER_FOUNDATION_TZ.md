# ANALYZER_FOUNDATION_TZ.md

Техническое задание на базу подключения анализаторов NOVA.

Цель: будущие анализаторы должны добавляться без изменения Matrix, Shadow, Laboratory и Autotuner. Любой анализатор может иметь свою внутреннюю математику, но наружу он обязан отдавать унифицированный пакет evidence.

Анализатор NOVA не является модулем торгового решения. Он не возвращает `buy/sell`, не голосует за направление и не решает вход/выход/стоп. Его задача — описать наблюдаемый феномен через evidence, context, constraints, zones, conflicts, invalidation hints, quality и lineage. Решение принадлежит отдельному контуру `DecisionEngine / TradeCalculator / RiskManager / SafetyKernel`.

## 1. Базовый поток

```text
AnalyzerContext
→ Analyzer.analyze(...)
→ AnalysisPackage
→ HistoryDB
→ Matrix Core / Validation Layer / Autotuner lineage
```

`AnalysisPackage` содержит:

- `AnalysisResult`;
- `CardDeck`;
- `ForecastContribution[]`;
- `StateContribution[]`.

Пакет не должен содержать плоский signal score вида `+1 long`, `-1 short`, `BUY`, `SELL`. Если старый или стандартный анализатор концептуально похож на сигнальный, адаптер NOVA обязан перевести его результат в карточки/контекст/ограничения без переноса сигнальной механики.

Не каждый анализатор обязан строить собственное поле/полотно. Field-like output разрешён только если у феномена есть естественная геометрия: price-time, price-volume, liquidity-depth, structure zones, regime surface. Иначе анализатор отдаёт cards/state/constraints. Поля разных типов соединяются позже через typed relations и lineage, а не через общий score.

## 2. AnalyzerManifest

`AnalyzerManifest` — паспорт анализатора.

Он нужен для:

- явной версии анализатора;
- понимания dependency group;
- списка требуемых входных данных;
- списка параметров, которые может настраивать Autotuner;
- понимания, какие стадии анализатор поддерживает: raw, validation, recheck.

Минимальные поля:

- `name`;
- `version`;
- `description`;
- `dependency_group`;
- `required_inputs`;
- `supported_timeframes`;
- `output_card_types`;
- `parameter_names`;
- `supports_raw`;
- `supports_validation`;
- `supports_recheck`.

## 3. AnalyzerContext

`AnalyzerContext` — frozen context одного запуска анализатора.

Он задаёт:

- `run_id`;
- `cycle_id`;
- `symbol`;
- `timeframe`;
- `profile_id`;
- `parameters`;
- `market_snapshot_id`;
- `available_data_ids`;
- `stage`;
- `input_matrix_id`;
- `feedback_depth`;
- `parent_card_ids`.

Рыночные данные должны попадать к анализатору через NOVA data contracts, прежде всего `MarketSnapshot`, а не через raw Binance JSON.

RAW анализ:

```text
stage = RAW
input_matrix_id = None
feedback_depth = 0
```

Validation анализ:

```text
stage = VALIDATION
input_matrix_id = MATRIX_...
feedback_depth = 1
```

Так сохраняется no-echo граница.

## 4. AnalysisPackage

`AnalysisPackage` — единый конверт результата.

Одинаковый формат используется и для raw анализа, и для validation/revision/recheck, но права влияния задаются карточками и stage/tier metadata.

Это позволяет HistoryDB, Matrix, Shadow, Laboratory и Autotuner читать результаты одинаково, не зная внутренности конкретного анализатора.

## 5. BaseAnalyzer

`BaseAnalyzer` — общий разъём.

Любой будущий анализатор должен иметь:

```text
manifest
analyze(context) -> AnalysisPackage
```

Асинхронность можно добавить позже на уровне runner/orchestrator. До этого анализаторы не должны писать напрямую в общую матрицу или общий state. Они только читают context и возвращают package.

## 6. AnalyzerRegistry

`AnalyzerRegistry` — явный список подключённых анализаторов.

Он нужен для:

- ручной регистрации без магии автозагрузки;
- проверки дублей;
- получения manifest;
- запуска raw/validation/recheck групп.

На раннем этапе NOVA не использует plugin discovery, чтобы загрузка анализаторов была прозрачной.

## 7. AnalyzerRunner

`AnalyzerRunner` запускает анализаторы стадиями:

```text
run_raw_pass()
run_validation_pass()
```

Правило:

- raw pass не получает matrix ID;
- validation pass обязан иметь `input_matrix_id`;
- runner собирает packages, но не строит матрицу сам;
- матрица строится отдельным этапом после сбора packages.

Runner также не агрегирует анализаторы в голосование. Его роль — stage separation, lineage и доставка packages до следующего слоя.

Это позволяет позже безопасно распараллелить анализаторы без гонки данных.

## 8. Fixture analyzer

`StaticTestAnalyzer` — не торговый анализатор.

Он нужен только для проверки трубы:

```text
AnalyzerRunner
→ AnalysisPackage
→ CardDeck
→ ForecastContribution
→ HistoryDB
→ MatrixValidator
```

Реальные анализаторы будут добавляться позже.

## 9. Расширяемая HistoryDB

HistoryDB должна работать с минимальным наполнением сейчас и не ломаться при расширении контекста потом.

Принцип:

- важные lineage/search поля — отдельные колонки;
- расширяемый контекст — `payload_json`;
- каждая таблица имеет `schema_version`.

Базовые таблицы:

- `analysis_results`;
- `evidence_cards`;
- `forecast_contributions`;
- `state_contributions`;
- `forecast_matrices`;
- `matrix_zones`;
- `state_matrices`.

Эти таблицы должны быть пригодны для Autotuner, Shadow и Laboratory без будущей переделки базовой истории.

## 10. Следующий шаг после базы

После Analyzer Foundation следующим этапом реализуется:

```text
ForecastMatrixEngine Core
```

Он будет читать raw primary packages/cards/contributions и строить primary/reconciled matrix layers.
