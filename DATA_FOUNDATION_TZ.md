# DATA_FOUNDATION_TZ.md

Техническое задание на унифицированный слой данных NOVA.

Цель: Binance REST/WS, синтетические таймфреймы, новости и будущие источники должны приводиться к внутренним моделям NOVA до попадания в анализаторы. Анализаторы не должны зависеть от raw JSON конкретной биржи или API.

## 1. Основное правило

```text
External source payload
→ NOVA data model
→ AnalyzerContext / AnalysisPackage
→ Matrix / Shadow / Autotuner lineage
```

Нельзя отдавать анализаторам сырой Binance response как основной контракт.

Data layer не выдаёт торговых сигналов и не принимает решений. Он поставляет только нормализованные факты, lineage, quality, freshness, gaps, cache/snapshot state и reconciliation metadata. Любая логика `buy/sell/long/short/stop` вне TradeCalculator/RiskManager запрещена.

## 2. Data inventory по старым анализаторам

| Старый модуль | Будущая роль NOVA | Нужные данные | NOVA-модели |
| --- | --- | --- | --- |
| `market_analyzer.py` | `MarketStructureAnalyzer` | OHLCV candles | `Candle`, `CandleSeries`, `MarketSnapshot` |
| `market_regime.py` | state/regime analyzer | multi-TF OHLCV | `MarketSnapshot.candles` |
| `fractal_analysis.py` | structural level analyzer | OHLCV candles | `CandleSeries` |
| `pattern_recognition.py` | pattern analyzer | OHLCV candles | `CandleSeries` |
| `volume_profile.py` | volume/value area analyzer | candles now, aggTrades later | `CandleSeries`, `AggTradeSeries` |
| `orderbook_analysis.py` | liquidity analyzer | orderbook depth | `OrderbookSnapshot`, `OrderbookLevel` |
| `derivatives_analyzer.py` | futures pressure/state analyzer | funding, OI, long/short | `DerivativesSnapshot` |
| `btc_correlation.py` | correlation/validation analyzer | primary + BTC candles | `MarketSnapshot.related_candles` |
| `multi_tf_context.py` | validation/reconciliation layer | multi-TF candles + analysis outputs | `MarketSnapshot`, cards/matrices |
| `synthetic_timeframes.py` | data builder, not analyzer | base timeframe candles | `CandleSeries` with `DataSourceType.SYNTHETIC` |
| `data_manager.py` | data layer, not analyzer | REST/WS/cache | `MarketSnapshot`, source refs, quality |
| `news_sentiment.py` | late state/context analyzer | RSS/news/API | `NewsItem`, `NewsBatch` |

## 3. Базовые модели

Реализованы в `nova/data/models.py`:

- `DataSourceRef`;
- `DataQualityReport`;
- `Candle`;
- `CandleSeries`;
- `OrderbookLevel`;
- `OrderbookSnapshot`;
- `AggTrade`;
- `AggTradeSeries`;
- `FundingRate`;
- `OpenInterestPoint`;
- `LongShortRatioPoint`;
- `DerivativesSnapshot`;
- `NewsItem`;
- `NewsBatch`;
- `MarketSnapshot`.

## 4. Source lineage

Каждый data object должен иметь источник:

```text
BINANCE_REST
BINANCE_WS
SYNTHETIC
INTERNAL
RSS
FIXTURE
UNKNOWN
```

Источник хранится через `DataSourceRef`.

Это нужно, чтобы Autotuner и Shadow могли различать:

- REST candles;
- WS candles;
- synthetic TF;
- orderbook snapshot;
- RSS/news;
- fixture/test data.

## 5. Quality contract

Каждый крупный набор данных должен иметь `DataQualityReport`:

- `is_usable`;
- `score`;
- `completeness`;
- `freshness_sec`;
- `gap_count`;
- `issue_codes`;
- `notes`;
- `payload`.

Анализатор может отказаться от raw primary output, если quality не проходит его минимальные требования.

## 6. MarketSnapshot

`MarketSnapshot` — единая точка входа для анализаторов.

Он может содержать:

- candles основного символа по TF;
- related candles, например BTCUSDT;
- orderbook snapshot;
- aggTrades;
- derivatives snapshot;
- news batch;
- общий quality report.

Первый рабочий анализатор должен читать данные из `MarketSnapshot`, а не из raw Binance JSON.

## 7. Binance REST/WS порядок

Правильный порядок реализации:

1. Data models;
2. Binance REST adapter, возвращающий NOVA models;
3. cache/reconciliation/data quality;
4. WS live updates;
5. analyzers.

REST нужен для warmup/backfill/reconciliation. WS может использовать публичный stream API для live updates, но не должен становиться единственным источником истины.

Рабочий поток:

```text
REST warmup 300x5m
→ CandleCache
→ SyntheticTimeframeBuilder: 10m/15m/30m/1h/4h/8h/12h
→ MarketSnapshot
→ SystemSupervisor logs snapshot and passes it to CycleRunner
→ WS kline updates for closed base-TF candles
→ CandleCache update + synthetic TF rebuild
→ WS loop stops/reconnects by policy and logs aggregate lifecycle
→ REST reconciliation refreshes recent base candles, rebuilds synthetic TF and emits a current MarketSnapshot
```

Для старших TF можно дополнительно скачать native candles REST-ом за сопоставимый период и использовать их для reconciliation/quality, но synthetic TF остаются помеченными как производные.

Важно: не каждый synthetic TF имеет native Binance interval. Например, `10m` строится из `5m`, но не сверяется как native interval, если биржа такой interval не поддерживает. Это записывается как `native_interval_not_supported`, а не как ошибка прогрева.

## 7.1 Кэширование

Кэширование нужно сразу, но в два уровня:

1. **In-memory rolling cache сейчас** — `CandleCache` хранит прогретые REST candles и обновления WS. Анализаторы читают данные из snapshot/cache, а не напрямую из Binance.
2. **Persistent raw candle archive позже** — понадобится для ускорения рестартов, backtests, лаборатории и больших исторических прогонов. На текущем этапе не пишем каждую свечу в SQLite как основную историю, чтобы не раздувать БД до появления политики retention.

На текущем этапе HistoryDB сохраняет `MarketSnapshot` как payload для lineage/debug. Это не замена полноценному candle archive.

## 7.2 Логирование

Логирование делится на два слоя:

- `EventLog` JSONL — append-only журнал фактов: warmup started/completed/failed, snapshot created, matrix built, trade plan created.
- `HistoryDB` SQLite — queryable memory: market snapshots, analysis packages, cards, contributions, matrices, plans and outcomes.

Data warmup должен писать события уровня процесса и сохранять snapshot metadata/payload. Высокочастотные WS ticks не должны писаться в EventLog по одному событию; они идут через cache, а в журнал попадают агрегированные состояния/ошибки/reconnect events.

WS kline rule: public stream сообщения принимаются только как обновление OHLCV cache. В cache попадают закрытые candles базового TF; незакрытые kline ticks используются только как stream liveness/probe signal и не становятся evidence. После принятой закрытой свечи synthetic TF пересобираются как производные `ohlcv_resampled`.

WS loop rule: reconnect/backoff/heartbeat живут на data/supervisor уровне. EventLog не получает каждый tick; он получает `WS_KLINE_LOOP_STARTED` и `WS_KLINE_LOOP_STOPPED` с агрегатами: message count, open/closed candle counts, reconnect count, stopped reason, issue codes. Текущий `nova.main` остаётся bounded runtime slice, а не бесконечным daemon; полноценный daemon supervisor добавляется отдельным шагом.

Runtime transition rule: после успешного REST warmup `SystemSupervisor` сохраняет `MarketSnapshot`, пишет `DATA_WARMUP_COMPLETED`/`MARKET_SNAPSHOT_CREATED` и запускает цикл уже со статусом `market_snapshot_ready`. Если warmup падает, цикл остаётся безопасным `HOLD`, а анализаторы/Matrix не стартуют.

## 8. Synthetic TF rule

Синтетические таймфреймы являются производными от base timeframe. Они полезны как масштабные линзы, но не являются независимыми evidence и не являются голосами.

Они должны иметь:

```text
source_type = SYNTHETIC
dependency_group = ohlcv_resampled
parent/base series lineage в payload
```

Timeframe role rule:

- `5m` base TF даёт локальную динамику и оперативную свежесть;
- `10m/15m/30m/1h` synthetic TF дают контекст устойчивости/структуры;
- `4h/8h/12h` synthetic TF дают крупный контекст/режим/границы риска;
- native higher TF REST используется для reconciliation/quality/corroboration, но не становится независимым торговым голосом.

Запрещено считать multi-TF как арифметику `5m +1`, `1h +1`, `4h -1`. TF должны попадать дальше как context/constraints/conflict/lineage, а не как buy/sell score.

## 9. Следующий шаг

После WS kline loop slice:

```text
Periodic REST reconciliation + snapshot refresh → Matrix Core + first MarketStructureAnalyzer
```

Data Layer v0 содержит:

- `BinanceRestClient`: `ping`, `server_time`, `get_klines`, `get_orderbook`, `get_ticker_price`;
- `BinanceWsClient`: public kline stream URL builder and kline parser;
- `CandleCache`;
- `SyntheticTimeframeBuilder`;
- `TimeframeReconciler`;
- `DataScheduler`.
- `MarketDataWarmupService`: REST warmup → cache → synthetic TF → native higher-TF reconciliation → MarketSnapshot.
- `SystemSupervisor` runtime transition: warmup lifecycle events → snapshot logging → `CycleRunner` receives current `MarketSnapshot`.
- `WsKlineCacheUpdater`: public WS kline startup probe, closed base-TF candle cache update, synthetic TF rebuild, aggregate stream lifecycle logging.
- `WsKlineStreamLoop`: bounded WS kline runtime slice with reconnect/backoff policy and aggregate lifecycle logging.
- `MarketSnapshotRefreshService`: recent REST kline reconciliation over `CandleCache`, synthetic TF rebuild and refreshed `MarketSnapshot` for `CycleRunner`.

Торговые операции и LIVE execution не входят в этот шаг.
