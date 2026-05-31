# Shadow and Laboratory Model

Документ фиксирует смысл, чтобы Shadow/Lab не превратились в дубль рабочего
контура. Они исследуют причины, запреты, недоверие/переоценку и альтернативные
сценарии по тем же сохранённым снимкам и lineage.

## Single calculation engine

`ScenarioEvaluator` is the only engine that calculates alternative scenario outcomes.

It evaluates:

- HOLD shadow scenarios
- forbidden-action shadow scenarios: what would have happened if a blocked candidate had been allowed
- lab experiments
- matrix validation scenarios
- parameter sweeps
- alternative SL/TP/trailing variants

## ShadowEngine

Online component. Creates scenario requests from current HOLD, non-selected candidates and explicitly forbidden candidates.

Главная функция теневика — не просто "а что если вместо бездействия", а проверка запретов:

- какой кандидат был запрещён;
- каким правилом/модулем он был запрещён;
- какие snapshot/matrix/state условия были известны на тот момент;
- что бы произошло, если бы запрет не сработал;
- запрет увеличил результат, спас от просадки или был чрезмерно строгим;
- какие параметры/условия запрета стоит передать Autotuner/Lab на изучение.

Теневой расчёт должен использовать тот же канонический envelope расчёта, что и рабочий контур, но с явной меткой источника (`SHADOW_FORBIDDEN`, `SHADOW_ALTERNATIVE`, `HOLD_SHADOW`) и ссылкой на исходный snapshot/plan/candidate. Он не исполняется и не подмешивается в реальные результаты.

## Laboratory

Laboratory does not calculate PnL. It studies episodes, generates hypotheses and sends `ScenarioRequest` to `ScenarioEvaluator`.

Лаборатория должна отдельно искать:

- слишком доверенные области/карточки/параметры: система дала высокое доверие, а дальнейший путь показал слабость;
- недооценённые области/карточки/параметры: система дала низкое доверие или запрет, а сценарий оказался полезным;
- условия, при которых запрет был полезен;
- условия, при которых запрет был чрезмерным;
- recheck/tension patterns, которые заранее показывали неопределённость.

Лаборатория не заменяет теневик: теневик собирает онлайн-контрфакты рядом с текущим циклом, лаборатория потом системно перебирает сохранённые эпизоды и проверяет гипотезы пакетно.

## Market video

Laboratory should learn from `MarketEpisode`, not only one snapshot. Episode includes pre-trade and in-trade dynamics: matrix slope, confidence trend, volatility, liquidity, MFE/MAE and exit pressure.

## Tags matter

Every outcome must be tagged by source:

- `REAL_EXECUTION`
- `HOLD_SHADOW`
- `SHADOW_FORBIDDEN`
- `SHADOW_ALTERNATIVE`
- `LAB_EXPERIMENT`
- `LAB_OVERTRUSTED_CHECK`
- `LAB_UNDERTRUSTED_CHECK`
- `MATRIX_VALIDATION`
- `PARAMETER_SWEEP`

Autotuner uses tags to decide which sources deserve trust.
