# 🎯 ПЛАН ИНТЕГРАЦИИ МАТРИЦЫ ПРОГНОЗОВ
## Ветка: 30.05.26-UNITED-VERSION

**Дата начала**: 30 мая 2026  
**Статус**: 🔵 ГОТОВ К СТАРТУ  
**Цель**: Интеграция системы прогнозирования через матрицу вероятностей

---

## 📋 ОБЩАЯ СТРУКТУРА

### Принципы работы:
1. **Никаких констант** - все параметры настраиваются автотюнером
2. **Гранулярное доверие** - доверие к каждому результату каждого анализатора на каждом ТФ в каждом режиме рынка
3. **Полные прогнозы** - анализаторы выдают ВСЕ возможные прогнозы, автотюнер решает каким доверять
4. **Адаптивный трейлинг** - без фиксированного TP, умное подтягивание SL через матрицу
5. **Стремление к 100WR/100PnL/0DD** - автотюнер оптимизирует все параметры

---

## 🎯 ЭТАП 1: МАТРИЦА ПРОГНОЗОВ (4-5 часов)

### 1.1 Расширить анализаторы для прогнозов

**Файлы для изменения**:
- `TENBID/analyzers/fractal_analysis.py`
- `TENBID/analyzers/market_analyzer.py`
- `TENBID/analyzers/pattern_recognition.py`

**Формат прогноза** (детальный):
```python
{
    "current_state": {
        # Текущие данные анализатора (как есть)
    },
    "forecasts": [
        {
            "timeframe": "5m",              # На каком ТФ прогноз
            "time_offset_min": 15,          # Через сколько минут
            "scenario": "BREAKOUT_UP",      # Сценарий
            "price_range": {
                "min": 0.385,               # Минимальная цена
                "max": 0.395,               # Максимальная цена
                "most_likely": 0.390        # Наиболее вероятная
            },
            "confidence": 0.7,              # Уверенность анализатора (0-1)
            "factors": [                    # Факторы, влияющие на прогноз
                "support_hold",
                "volume_increase",
                "trend_continuation"
            ],
            "metadata": {                   # Дополнительные данные
                "strength": 0.8,            # Сила сигнала
                "volatility": 0.05          # Ожидаемая волатильность
            }
        }
        # ... другие прогнозы на разные горизонты
    ]
}
```

**Требования**:
- ✅ Каждый анализатор выдаёт прогнозы на ВСЕ доступные горизонты
- ✅ Прогнозы для каждого ТФ отдельно
- ✅ Никаких заглушек - только реальные расчёты
- ✅ Полная совместимость с существующей архитектурой

**Статус**: ⏳ Ожидает выполнения

---

### 1.2 Доработать probability_matrix.py

**Файл**: `TENBID/core/probability_matrix.py`

**Реализация**:
```python
class ProbabilityMatrix:
    """
    Многомерное поле вероятностей с Grid + Gaussian Blur аппроксимацией.
    
    Оси:
    - Время (минуты от текущего момента)
    - Цена (уровни цены)
    - Таймфрейм (5m, 15m, 1h, 4h)
    - Сценарий (TREND_UP, BREAKOUT_UP, PULLBACK, etc)
    
    Методы:
    - add_forecast() - добавить прогноз с учётом доверия
    - apply_blur() - применить Gaussian blur для сглаживания
    - find_max_probability_zones() - найти зоны максимальной вероятности
    - get_forecast_at() - получить прогноз для конкретного времени/цены
    - clear() - очистить матрицу для нового цикла
    """
```

**Параметры от автотюнера**:
- `matrix_time_resolution` - шаг по времени (минуты)
- `matrix_price_resolution` - шаг по цене (%)
- `blur_radius` - радиус Gaussian blur
- `min_probability_threshold` - минимальный порог вероятности

**Требования**:
- ✅ Быстрый поиск зон (O(1) после построения)
- ✅ Все параметры настраиваются автотюнером
- ✅ Поддержка множественных сценариев
- ✅ Эффективное использование памяти

**Статус**: ⏳ Ожидает выполнения

---

### 1.3 Интегрировать матрицу в main.py

**Файл**: `TENBID/main.py`

**Изменения**:
```python
# Инициализация
matrix = ProbabilityMatrix(config, autotuner)

# В основном цикле:
for cycle in trading_loop:
    # 1. Получить прогнозы от всех анализаторов
    all_forecasts = collect_forecasts(analyzers_results)
    
    # 2. Применить гранулярное доверие от автотюнера
    weighted_forecasts = apply_trust_weights(all_forecasts, autotuner)
    
    # 3. Заполнить матрицу
    matrix.clear()
    for forecast in weighted_forecasts:
        matrix.add_forecast(forecast)
    matrix.apply_blur()
    
    # 4. Матрица готова для TradeCalculator
    # (используется на следующих этапах)
```

**Требования**:
- ✅ Сбор прогнозов от всех анализаторов
- ✅ Применение гранулярного доверия (анализатор + ТФ + метрика + режим)
- ✅ Обновление матрицы каждый цикл
- ✅ Логирование для отладки

**Статус**: ⏳ Ожидает выполнения

---

## 🎯 ЭТАП 2: TRADE CALCULATOR (2-3 часа)

### 2.1 Создать core/trade_calculator.py

**Файл**: `TENBID/core/trade_calculator.py` (новый)

**Структура**:
```python
class TradeCalculator:
    """
    Полный просчёт сделки на основе матрицы прогнозов.
    
    Функционал:
    1. Анализ матрицы - поиск оптимальных зон входа
    2. Расчёт точки входа (может быть лимитный ордер)
    3. Расчёт SL на основе прогноза матрицы
    4. Расчёт затрат (комиссии, спред, проскальзывание)
    5. Расчёт ожидаемой чистой прибыли
    6. Принятие решения: OPEN/HOLD
    """
    
    def __init__(self, config, autotuner):
        # Все параметры от автотюнера
        self.params = autotuner.get_trade_calculator_params()
    
    def calculate_trade(self, matrix, current_price, market_context):
        """
        Полный просчёт сделки.
        
        Returns:
            {
                'decision': 'OPEN' | 'HOLD',
                'entry_price': float,
                'sl_price': float,
                'expected_profit_pct': float,
                'net_profit_pct': float,  # После вычета затрат
                'costs': {
                    'commission': float,
                    'spread': float,
                    'slippage': float,
                    'total': float
                },
                'horizon_minutes': int,
                'confidence': float,
                'reasoning': str  # Объяснение решения
            }
        """
```

**Логика расчёта**:
1. Найти в матрице зоны максимальной вероятности роста/падения
2. Определить оптимальную точку входа
3. Рассчитать SL на основе прогноза (не фиксированный %)
4. Вычислить все затраты
5. Если net_profit > порог от автотюнера → OPEN

**Требования**:
- ✅ Все параметры от автотюнера
- ✅ Учёт реальных затрат
- ✅ Детальное логирование решений
- ✅ Никаких хардкодов

**Статус**: ⏳ Ожидает выполнения

---

## 🎯 ЭТАП 3: АДАПТИВНЫЙ ТРЕЙЛИНГ (2 часа)

### 3.1 Создать trading/adaptive_trailing.py

**Файл**: `TENBID/trading/adaptive_trailing.py` (новый)

**Структура**:
```python
class AdaptiveTrailing:
    """
    Адаптивный трейлинг стоп на основе матрицы прогнозов.
    
    Логика:
    1. Как можно быстрее переместить SL в безубыток
    2. Подтягивать SL с учётом:
       - ATR (не выбить раньше времени)
       - Прогноза матрицы (куда движется цена)
       - Параметров автотюнера (агрессивность)
    3. Баланс: не слишком близко, не слишком далеко
    """
    
    def __init__(self, config, autotuner):
        self.params = autotuner.get_trailing_params()
    
    def update_trailing(self, trade, matrix, current_price, atr):
        """
        Обновить уровень трейлинг стопа.
        
        Args:
            trade: Активная сделка
            matrix: Матрица прогнозов
            current_price: Текущая цена
            atr: Текущий ATR
        
        Returns:
            {
                'new_sl': float,
                'action': 'MOVE_TO_BREAKEVEN' | 'TRAIL' | 'HOLD',
                'distance_from_price': float,
                'reasoning': str
            }
        """
```

**Логика**:
```python
# Приоритет 1: Безубыток
if in_profit and not at_breakeven:
    return move_to_breakeven()

# Приоритет 2: Адаптивное подтягивание
forecast = matrix.get_forecast_at(current_time + horizon)
if forecast.probability_down > threshold:
    # Прогноз ухудшился - подтянуть стоп ближе
    return aggressive_trail()
else:
    # Прогноз хороший - дать цене расти
    return conservative_trail()
```

**Требования**:
- ✅ Быстрый переход в безубыток
- ✅ Учёт ATR для волатильности
- ✅ Использование прогноза матрицы
- ✅ Все параметры от автотюнера

**Статус**: ⏳ Ожидает выполнения

---

## 🎯 ЭТАП 4: РАСШИРЕНИЕ АВТОТЮНЕРА (2-3 часа)

### 4.1 Гранулярное доверие

**Файл**: `TENBID/core/autotuner.py`

**Структура доверия**:
```python
trust = {
    'Fractal': {
        '5m': {
            'support_levels': {
                'TRENDING': 0.95,
                'FLAT': 0.65,
                'VOLATILE': 0.70
            },
            'resistance_levels': {
                'TRENDING': 0.85,
                'FLAT': 0.60,
                'VOLATILE': 0.65
            }
        },
        '1h': {
            'support_levels': {
                'TRENDING': 0.90,
                'FLAT': 0.75,
                'VOLATILE': 0.80
            }
        }
    },
    'Pattern': {
        '15m': {
            'breakout': {
                'TRENDING': 0.80,
                'FLAT': 0.50
            }
        }
    }
    # ... для всех анализаторов
}
```

**Методы**:
```python
def get_trust(analyzer, timeframe, metric, market_regime):
    """Получить доверие для конкретного результата"""

def update_trust(trade_outcome):
    """Обновить доверие на основе результата сделки"""

def apply_trust_to_forecast(forecast):
    """Применить доверие к прогнозу"""
```

**Статус**: ⏳ Ожидает выполнения

---

### 4.2 Настройка параметров всех модулей

**Файл**: `TENBID/core/autotuner.py`

**Параметры для настройки**:
```python
# Матрица
matrix_params = {
    'time_resolution': 5,      # минут
    'price_resolution': 0.5,   # %
    'blur_radius': 2.0
}

# TradeCalculator
trade_calc_params = {
    'min_net_profit': 0.3,     # %
    'max_entry_delay': 10,     # минут
    'sl_safety_margin': 1.2    # множитель
}

# Трейлинг
trailing_params = {
    'breakeven_trigger': 0.3,  # % прибыли для безубытка
    'atr_multiplier': 1.5,     # множитель ATR
    'aggressiveness': 0.7      # 0-1
}
```

**Оптимизация**:
```python
def optimize_all_parameters():
    """
    Анализирует последние 100 сделок и оптимизирует:
    1. Гранулярное доверие
    2. Параметры матрицы
    3. Параметры TradeCalculator
    4. Параметры трейлинга
    
    Цель: 100WR / 100PnL / 0DD
    """
```

**Статус**: ⏳ Ожидает выполнения

---

## 🎯 ЭТАП 5: ИНТЕГРАЦИЯ И ТЕСТЫ (1-2 часа)

### 5.1 Интеграция в main.py

**Файл**: `TENBID/main.py`

**Полный цикл**:
```python
# Инициализация
matrix = ProbabilityMatrix(config, autotuner)
trade_calculator = TradeCalculator(config, autotuner)
adaptive_trailing = AdaptiveTrailing(config, autotuner)

# Основной цикл
while trading:
    # 1. Получить данные и анализ
    data = get_market_data()
    analysis = run_analyzers(data)
    
    # 2. Построить матрицу прогнозов
    matrix.clear()
    for analyzer_result in analysis:
        for forecast in analyzer_result['forecasts']:
            trust = autotuner.get_trust(...)
            matrix.add_forecast(forecast, trust)
    matrix.apply_blur()
    
    # 3. Управление активными позициями
    for trade in active_trades:
        trailing_update = adaptive_trailing.update_trailing(
            trade, matrix, current_price, atr
        )
        if trailing_update['action'] == 'MOVE_TO_BREAKEVEN':
            move_sl(trade, trade.entry_price)
        elif trailing_update['action'] == 'TRAIL':
            move_sl(trade, trailing_update['new_sl'])
    
    # 4. Поиск новых сделок
    if no_active_trades:
        trade_plan = trade_calculator.calculate_trade(
            matrix, current_price, market_context
        )
        if trade_plan['decision'] == 'OPEN':
            open_trade(trade_plan)
    
    # 5. Обновление автотюнера
    if cycle % 10 == 0:
        autotuner.optimize_all_parameters()
```

**Статус**: ⏳ Ожидает выполнения

---

### 5.2 Финальное тестирование

**Проверки**:
- ✅ Синтаксис всех файлов
- ✅ Импорты работают
- ✅ Матрица строится корректно
- ✅ TradeCalculator принимает решения
- ✅ Трейлинг обновляется
- ✅ Автотюнер сохраняет параметры
- ✅ Сухой запуск 5-10 минут

**Статус**: ⏳ Ожидает выполнения

---

## 📊 ПРОГРЕСС

```
Этап 1.1: ░░░░░░░░░░░░░░░░░░░░   0%
Этап 1.2: ░░░░░░░░░░░░░░░░░░░░   0%
Этап 1.3: ░░░░░░░░░░░░░░░░░░░░   0%
Этап 2:   ░░░░░░░░░░░░░░░░░░░░   0%
Этап 3:   ░░░░░░░░░░░░░░░░░░░░   0%
Этап 4.1: ░░░░░░░░░░░░░░░░░░░░   0%
Этап 4.2: ░░░░░░░░░░░░░░░░░░░░   0%
Этап 5.1: ░░░░░░░░░░░░░░░░░░░░   0%
Этап 5.2: ░░░░░░░░░░░░░░░░░░░░   0%
─────────────────────────────────
ИТОГО:    ░░░░░░░░░░░░░░░░░░░░   0%
```

**Ожидаемое время**: 10-13 часов

---

## 🔄 ЖУРНАЛ ИЗМЕНЕНИЙ

### 30.05.2026 - Создание плана
- ✅ Создан детальный план интеграции
- ✅ Определён формат прогнозов
- ✅ Выбран метод аппроксимации (Grid + Blur)
- ✅ Согласована архитектура всех модулей

---

## 💡 ВАЖНЫЕ ПРИНЦИПЫ

1. **Никаких заглушек** - только полностью рабочий код
2. **Никаких хардкодов** - все параметры от автотюнера
3. **Полная совместимость** - с существующей архитектурой
4. **Гранулярность** - доверие к каждому результату отдельно
5. **Адаптивность** - всё настраивается автоматически
6. **Цель** - 100WR / 100PnL / 0DD

---

## 📝 ПРИМЕЧАНИЯ

- План можно выполнять поэтапно
- Каждый этап независим и может быть остановлен
- После каждого этапа - коммит в Git
- Тестирование после каждого этапа
- Консультация перед любыми отклонениями от плана

---

**Статус**: 🟢 ГОТОВ К ВЫПОЛНЕНИЮ
**Следующий шаг**: Этап 1.1 - Расширение анализаторов
