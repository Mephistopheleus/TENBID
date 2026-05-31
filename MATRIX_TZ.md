# MATRIX_TZ.md

Техническое задание и архитектурные ремарки по Matrix Core NOVA.

Этот документ фиксирует договорённость: матрица NOVA — не таблица сигналов и не механизм прямого торгового решения. Матрица является разреженным доказательным полем (`sparse evidence field`), которое хранит зоны смысла, их происхождение, конфликтность, необходимость перепроверки и пригодность для дальнейшего решения.

## 0. Непереговорная терминология NOVA

В NOVA никто не голосует и никто, кроме выделенного контура расчёта сделки/риска, не принимает торговое решение.

Запрещённая рамка мышления для архитектуры:

```text
analyzer says buy/sell
timeframe votes +1/-1
matrix aggregates votes
```

Правильная рамка NOVA:

```text
Data / Analyzer / Matrix
→ evidence, context, constraints, zones, conflicts, quality, lineage, uncertainty
→ Decision / TradeCalculator / RiskManager
→ допустимый или недопустимый TradePlan
```

Анализаторы, таймфреймы, карточки и матрица не выдают `buy`, `sell`, `long`, `short`, `stop` как решение. Они описывают ситуацию, границы, сценарные области, противоречия, качество и условия invalidation. Сделочный план, размер, риск, costs, допустимость входа/выхода и режим исполнения принадлежат отдельному контуру `DecisionEngine / TradeCalculator / RiskManager / SafetyKernel`.

Это архитектурная защита уникального подхода NOVA. Старый сигнальный подход "как у всех" запрещён, потому что он разрушает карточную lineage-модель, no-echo правило, sparse evidence field и будущий Shadow/Autotuner.

## 1. Жёсткая цель

Построить Matrix Core, который:

1. принимает типизированную колоду доказательств и/или стандартизированные contributions;
2. строит только локальные evidence-backed зоны;
3. не заполняет пустоту искусственными вероятностями;
4. различает первичные данные, валидацию, ревизию и recheck;
5. не допускает эффекта эха;
6. сохраняет lineage до analyzer/card/contribution;
7. отдаёт DecisionEngine контекст, но не принимает сделочное решение сам.

## 2. Главная модель

Матрица — это `sparse evidence field`.

Прогноз или карточка не создаёт плоский голос и не является торговым сигналом. Она создаёт локальное поле:

- `CORE` — область, которую evidence прямо описывает;
- `HALO` — ограниченный ореол неопределённости вокруг core;
- `BRIDGE` — поддержанная связь между близкими совместимыми областями;
- `TENSION` — область противоречия между близкими несовместимыми областями.

Где нет evidence — там пустота. Глобальный blur запрещён.

## 3. Острова смысла

MatrixZone — это остров смысла, а не торговый приказ.

Остров может:

- иметь core/halo границы;
- быть усилен пересечением совместимых evidence;
- получить bridge к соседней совместимой зоне;
- получить tension при конфликте;
- запросить recheck;
- стать stale/invalidated/confirmed;
- хранить contributor/card lineage.

Если две зоны рядом, но не полностью совпадают, область между ними может стать bridge только при совместимости по смыслу, горизонту, направлению/сценарию, цене и феномену. Если смысл конфликтует — это tension, а не усреднение.

## 4. Карточная модель

Анализаторы могут выдавать не один плоский результат, а колоду карточек.

Базовые типы:

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

Каждая карточка обязана иметь:

- `card_type`;
- `stage`;
- `tier`;
- `cycle_id`;
- `input_matrix_id`, если карточка появилась после просмотра матрицы;
- `feedback_depth`;
- `parent_card_ids`;
- `target_zone_ids`;
- `rights` — права влияния;
- `payload`;
- `evidence_refs`.

## 5. Права влияния карточек

Карточка не равна голосу, сигналу или решению. Карточка имеет строго ограниченные права:

- `can_seed_field` — может создать первичное поле;
- `can_adjust_zone_metadata` — может менять agreement/conflict/status/recheck metadata;
- `can_request_recheck` — может запросить перепроверку;
- `can_affect_decision_context` — может попасть в контекст DecisionEngine;
- `can_affect_primary_statistics` — может участвовать в первичной статистике Autotuner.

Только raw primary forecast evidence с `feedback_depth = 0` может seed-ить primary matrix field.

## 6. No-echo rule

Главное правило:

> Primary matrix must not believe its own reflection within the same cycle.

То есть поток внутри цикла должен быть ацикличным:

```text
RAW analyzer/card evidence
→ Primary ForecastMatrix
→ validation / revision / recheck cards
→ DecisionContext / Scheduler / future reconciled layers
```

Запрещённый поток:

```text
RAW evidence
→ Matrix
→ analyzer looks at Matrix
→ analyzer emits matrix-assisted forecast
→ same PrimaryMatrix treats it as independent primary evidence
```

Matrix-assisted cards/contributions должны иметь:

- `input_matrix_id`;
- `parent_card_ids` или `parent_analysis_result_ids`;
- `feedback_depth > 0`;
- `tier = META` или `DERIVED`;
- stage `VALIDATION`, `REVISION` или `RECHECK`.

Они могут менять metadata, trust, conflict, recheck и decision context, но не первичную статистику и не primary field той же матрицы.

## 6.1 Primary и Reconciled слои

Кроссвалидация не выкидывается из матрицы. Она живёт в отдельном/параллельном слое.

Минимальные слои:

- `PrimaryMatrix` — чистое первичное поле из `RAW / PRIMARY / feedback_depth = 0` evidence.
- `ValidationLayer` — validation/revision/recheck карточки, которые комментируют, уточняют или требуют перепроверки зон.
- `ReconciledMatrix` — рабочее уточнённое поле для DecisionEngine, построенное из primary field плюс validation/revision metadata без загрязнения primary statistics.

DecisionEngine может использовать ReconciledMatrix как более точную рабочую картину. Autotuner при этом обязан считать primary accuracy и matrix-assisted accuracy отдельно.

## 7. Evidence stages и tiers

Stages:

- `RAW` — первичный вывод без просмотра матрицы;
- `MATRIX_BUILD` — этап построения матрицы;
- `VALIDATION` — проверка уже построенных зон;
- `REVISION` — пересмотр интерпретации с учётом матрицы;
- `RECHECK` — запрос/результат перепроверки;
- `OUTCOME` — фактический исход;
- `TUNING` — вывод Autotuner.

Tiers:

- `PRIMARY` — независимое первичное evidence;
- `META` — комментарий, валидация, recheck, состояние;
- `DERIVED` — результат, полученный с использованием матрицы или других производных слоёв.

## 8. Validity и recheck

Сильный прогноз не должен просто тухнуть по таймеру.

Валидность зоны зависит от:

- времени;
- входа цены в halo/core;
- выхода цены из ожидаемой области;
- invalidation level;
- изменения волатильности;
- изменения ликвидности;
- появления tension/conflict;
- свежести данных;
- качества источников.

Если зона важная, матрица должна формировать recheck intent/card, а не пассивно ждать decay.

Матрица сама не запускает анализаторы. Она маркирует необходимость внимания для Supervisor/Scheduler.

## 9. Что Matrix Core должен реализовать первым

Минимальная рабочая реализация Matrix Core должна:

1. принять `ForecastContribution` и/или `CardDeck`;
2. отфильтровать primary field seeds через `MatrixValidator`;
3. создать `CORE` зоны из raw primary evidence;
4. создать ограниченный `HALO` вокруг core;
5. объединять совместимые пересечения;
6. создавать `BRIDGE` между близкими совместимыми островами;
7. создавать `TENSION` между близкими несовместимыми островами;
8. считать `agreement_score`, `conflict_score`, `importance_score`;
9. сохранять `contributor_ids`, `source_analysis_result_ids`, `source_card_ids`;
10. выставлять `recheck_reasons` для важных/сомнительных зон;
11. возвращать `ForecastMatrix(primary_only=True)`.

Если вход пустой, матрица возвращает пустой список зон. Это валидное состояние, а не ошибка.

## 10. StateMatrix v0

StateMatrix v0 должен:

1. принимать ForecastMatrix и state contributions;
2. выдавать trust/data_quality/conflict/liquidity/volatility state;
3. при отсутствии данных возвращать low-trust/no-data состояние;
4. учитывать tension/conflict из ForecastMatrix;
5. не принимать сделочное решение.

## 11. Runtime integration v0

Целевой путь:

```text
CycleRunner
→ collect raw evidence/cards/contributions
→ ForecastMatrixEngine Core
→ StateMatrixEngine
→ DecisionEngine
→ TradePlan
→ EventLog / HistoryDB
```

Даже до анализаторов runtime должен проходить через матрицу с пустым evidence и безопасным HOLD через DecisionEngine.

Обязательные события:

- `FORECAST_MATRIX_BUILT`
- `STATE_MATRIX_BUILT`
- `TRADE_PLAN_CREATED`

## 12. Autotuner rule

Autotuner обязан считать отдельно:

- raw primary evidence accuracy;
- matrix-assisted validation/revision behavior;
- recheck usefulness;
- final decision/outcome quality.

Нельзя смешивать raw primary и matrix-assisted evidence в одну статистику. Иначе эхо матрицы будет выглядеть как независимое подтверждение.

Autotuner не должен исправлять ошибочную сигнальную архитектуру. Он может настраивать параметры интерпретации, decay, penalties, sensitivity, risk/quality thresholds, но не превращает evidence в голоса и не должен учиться на модели `TF +1 / TF -1`. Если базовая структура неправильно смешивает dependent evidence, Autotuner только оптимизирует ошибку.

## 12.1 Timeframe role rule

Таймфрейм — это масштабная линза (`scale/context layer`), а не независимый участник голосования.

Примеры ролей TF:

- `local` — локальная динамика/структура/свежесть;
- `confirmation_context` — устойчивость или сомнительность локального феномена;
- `higher_context` — крупная зона, режим, граница риска, invalidation context;
- `regime` — широкое состояние рынка.

Даже native higher-TF candle с Binance не становится полностью независимым evidence, если описывает тот же рынок и тот же период. Native TF полезен для quality/reconciliation/corroboration, но не для механики "ещё один голос".

Synthetic TF должен иметь `dependency_group = ohlcv_resampled`. Native TF того же рынка должен рассматриваться как same-market aggregate/corroboration, а не внешний независимый источник. Конфликт между TF — это отдельный context/tension объект, а не арифметическая сумма сигналов.

## 13. Что не делать

Запрещено для Matrix Core:

- превращать карточки в плоские голоса;
- превращать таймфреймы в голоса или score counters;
- использовать лексику и механику сигналов buy/sell;
- строить `+1 long / -1 short` агрегацию;
- строить global blur по всей сетке;
- заполнять пустые области вероятностью;
- считать validation/revision первичным evidence;
- терять lineage при merge/bridge/tension;
- делать торговое решение внутри матрицы;
- копировать старые модули целиком.

## 14. Текущая реализация в коде

Уже заложено:

- `nova/core/evidence.py` — типы card/stage/tier/field role/status;
- `nova/cards/models.py` — `EvidenceCard`, `CardDeck`, `CardInfluenceRights`;
- `nova/analysis/models.py` — `AnalysisResult` и `StateContribution` с stage/tier/feedback lineage;
- `nova/matrix/models.py` — `ForecastContribution`, `MatrixZone`, `ForecastMatrix`, `StateMatrix` с matrix/card lineage;
- `nova/matrix/validators.py` — защита primary matrix от feedback-derived evidence;
- `nova/analyzers/contracts.py` — manifest/context/package/base analyzer contracts;
- `nova/analyzers/registry.py` — явный реестр анализаторов;
- `nova/analyzers/runner.py` — raw/validation runner со stage separation;
- `nova/analyzers/fixtures.py` — fixture analyzer для проверки трубы без реальных анализаторов;
- `nova/core/history_db.py` — расширяемая SQLite память для cards/contributions/matrices;
- `docs/MATRIX_MODEL.md` — концептуальная модель;
- `docs/AUTOTUNER_MODEL.md` — no-echo learning rule.

## 15. Следующий шаг

Следующий инженерный этап:

```text
Implement ForecastMatrixEngine Core
```

Не анализаторы. Не execution. Сначала живой Matrix Core:

```text
raw primary evidence → sparse islands → core/halo/bridge/tension → state → decision context
```
