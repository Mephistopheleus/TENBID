# 🚀 ПРЕДЗАПУСКОВЫЙ ЧЕКЛИСТ - TESTNET

## Дата: 2026-05-30
## Баланс: 50 USDT
## Режим: TESTNET (Binance Futures Testnet)
## Символ: DOGEUSDT

---

## ✅ ПРОВЕРКА СИНТАКСИСА

- [x] main.py - синтаксис корректен
- [x] autotuner.py - синтаксис корректен
- [x] trade_calculator.py - синтаксис корректен
- [x] adaptive_trailing.py - синтаксис корректен
- [x] probability_matrix.py - синтаксис корректен
- [x] market_analyzer.py - синтаксис корректен
- [x] fractal_analysis.py - синтаксис корректен
- [x] pattern_recognition.py - синтаксис корректен

---

## ✅ КОНФИГУРАЦИЯ

### config.ini
- [x] initial_balance = 50.0 USDT
- [x] mode = TESTNET
- [x] symbol = DOGEUSDT
- [x] API keys настроены (testnet)
- [x] base_url = https://testnet.binancefuture.com

### Параметры риска
- [x] min_position_pct = 1.0%
- [x] max_position_pct = 7.0%
- [x] min_sl_pct = 0.5%
- [x] max_sl_pct = 3.0%
- [x] target_rr_ratio = 2.0
- [x] max_daily_drawdown = 5.0%

---

## ✅ АРХИТЕКТУРА СИСТЕМЫ

### Модули интегрированы:
- [x] ProbabilityMatrix (Grid + Gaussian Blur)
- [x] TradeCalculator (анализ зон, расчёт затрат, решение OPEN/HOLD)
- [x] AdaptiveTrailing (breakeven + adaptive trailing)
- [x] Autotuner (гранулярное доверие + оптимизация параметров)

### Старые модули архивированы:
- [x] position_sizer.py → old_researches/
- [x] smart_trailing.py → old_researches/
- [x] README.md создан в old_researches/

---

## ✅ ЛОГИКА РАБОТЫ

### Цикл торговли:
1. [x] Анализаторы генерируют forecasts
2. [x] apply_granular_trust() применяет веса доверия
3. [x] ProbabilityMatrix обновляется прогнозами
4. [x] TradeCalculator анализирует зоны и принимает решение
5. [x] При OPEN: открытие позиции + AdaptiveTrailing
6. [x] При HOLD: shadow tracking для анализа
7. [x] Autotuner записывает результаты для оптимизации

### Управление позициями:
- [x] PositionManager отслеживает активные позиции
- [x] AdaptiveTrailing обновляет SL каждый цикл
- [x] Проверка SL/TP/Trailing каждый цикл
- [x] Запись результатов в Autotuner

---

## ✅ БАЗА ДАННЫХ

- [x] init_autotuner_db() вызывается при старте
- [x] Таблицы создаются автоматически:
  - trade_analysis_log
  - autotuner_logs
  - granular_trust_log
  - matrix_params_log
  - calculator_params_log
  - trailing_params_log

---

## ✅ ПАРАМЕТРЫ AUTOTUNER (по умолчанию)

### Matrix:
- time_horizon_minutes: 60
- time_resolution_minutes: 1.0
- price_levels: 100
- price_range_percent: 3.0
- blur_sigma_time: 2.0
- blur_sigma_price: 1.5
- min_probability_threshold: 0.55

### TradeCalculator:
- min_probability_threshold: 0.60
- min_net_profit_pct: 0.5%
- min_risk_reward_ratio: 1.5
- max_sl_percent: 2.0%
- sl_atr_multiplier: 1.5
- commission_percent: 0.1%
- spread_percent: 0.05%
- slippage_percent: 0.03%

### AdaptiveTrailing:
- breakeven_profit_pct: 0.5%
- breakeven_offset_pct: 0.1%
- atr_multiplier: 1.5
- aggressive_trail_factor: 0.7
- conservative_trail_factor: 1.3
- forecast_horizon_minutes: 15

---

## ⚠️ ВАЖНЫЕ МОМЕНТЫ

### НЕТ хардкода:
- [x] Все параметры от autotuner
- [x] Гранулярное доверие: analyzer+TF+metric+regime
- [x] Параметры загружаются из БД или дефолты

### Безопасность:
- [x] Testnet режим активен
- [x] Баланс 50 USDT (тестовые)
- [x] max_position_pct = 7% (макс 3.5 USDT на сделку)
- [x] max_sl_pct = 3% (макс 0.105 USDT риск)
- [x] max_daily_drawdown = 5% (макс 2.5 USDT потери в день)

### Логирование:
- [x] level = DEBUG
- [x] log_file = logs/tenbid.log
- [x] save_signals_to_db = true

---

## 🎯 ЦЕЛИ СИСТЕМЫ

- **WinRate:** стремление к 100%
- **PnL:** стремление к 100% в день
- **Drawdown:** стремление к 0%

**Метод:** Автоматическая оптимизация через autotuner на основе реальных результатов.

---

## 🚀 КОМАНДА ЗАПУСКА

```bash
cd /workspaces/TENBID/TENBID
python3 main.py
```

---

## 📊 ЧТО ОЖИДАТЬ

### Первый запуск:
1. Инициализация БД и таблиц
2. Загрузка 300 свечей для прогрева
3. Построение синтетических таймфреймов
4. Запуск Shadow Lab в фоне
5. Начало торгового цикла

### Каждый цикл (5 минут):
1. Обновление данных
2. Анализ всех анализаторов
3. Генерация прогнозов
4. Обновление матрицы вероятностей
5. Принятие решения (OPEN/HOLD)
6. Управление позициями (если есть)
7. Логирование результатов

### Логи будут показывать:
- 📊 Статистику матрицы
- 🎯 Топ зоны вероятности
- 🎲 Решения TradeCalculator
- 💰 Параметры сделок
- 📈 Обновления trailing stop
- ✅/❌ Результаты закрытых позиций

---

## ✅ СИСТЕМА ГОТОВА К ЗАПУСКУ!

**Все проверки пройдены. Можно запускать на testnet с балансом 50 USDT.**
