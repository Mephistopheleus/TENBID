# TENBID - Advanced Trading System with Full Logging and Auto-Tuning

## Overview

TENBID is a comprehensive cryptocurrency trading system for Binance (Testnet/Live) featuring:
- **Complete process logging** - Every signal, decision, and outcome is logged
- **Shadow mode calculations** - Test new parameters without risking real capital
- **Auto-tuning module** - Analyzes results and recommends parameter improvements
- **Probability field analysis** - Multi-factor probability assessment
- **Confidence scoring** - Trust-based confidence system for trade decisions
- **Risk management** - Comprehensive risk controls and position sizing

## Directory Structure

```
TENBID/
├── config/
│   └── config.ini          # Configuration file
├── logs/
│   ├── tenbid.log          # Main application log
│   ├── trades.jsonl        # Detailed trade log (JSON Lines)
│   ├── decisions.jsonl     # Decision-making log
│   └── shadow_calculations.jsonl  # Shadow mode results
├── modules/
│   ├── logger.py           # Comprehensive logging system
│   ├── autotuner.py        # Auto-tuning and recommendations
│   ├── binance_connector.py # Binance API connection
│   ├── math_analysis.py    # Technical indicators
│   ├── probability_field.py # Probability calculations
│   ├── confidence_system.py # Trust score system
│   ├── trade_calculator.py # Position sizing & calculations
│   ├── risk_manager.py     # Risk assessment
│   ├── shadow_calculator.py # Shadow mode calculations
│   └── trade_executor.py   # Order execution
└── README.md
```

## Key Features

### 1. Complete Logging (`modules/logger.py`)

Logs every aspect of the trading process:

```python
from modules.logger import get_logger

logger = get_logger()

# Log incoming signal
logger.log_signal({
    'symbol': 'BTCUSDT',
    'direction': 'LONG',
    'confidence': 85,
    'indicators': {'rsi': 25, 'macd': 'bullish'}
})

# Log decision with reasoning
logger.log_decision({
    'decision': 'OPEN',
    'reason': 'High confidence RSI oversold',
    'confidence_score': 85,
    'forbidden_reason': None,  # If trade was rejected
    'alternative_outcome': {...}  # What would happen if opened
})

# Log trade open with expected outcome
logger.log_trade_open({
    'trade_id': 'trade_001',
    'entry_price': 45000,
    'stop_loss': 44500,
    'take_profit': 46000,
    'expected_pnl_percent': 2.2
})

# Log trade close with actual vs expected
logger.log_trade_close({
    'trade_id': 'trade_001',
    'exit_price': 46000,
    'actual_pnl_percent': 2.2,
    'expected_pnl_percent': 2.2,
    'pnl_accuracy': 100.0,
    'close_reason': 'TAKE_PROFIT'
})
```

### 2. Auto-Tuning Module (`modules/autotuner.py`)

Analyzes historical trades and provides recommendations:

```python
from modules.autotuner import get_autotuner
from modules.logger import get_logger

autotuner = get_autotuner()
logger = get_logger()

# Run auto-tune analysis
result = autotuner.run_autotune_analysis(logger)

if result['status'] == 'COMPLETE':
    report = result['report']
    
    print(f"Analyzed {report['trades_analyzed']} trades")
    print(f"Current winrate: {report['performance_metrics']['winrate']}%")
    
    # Get recommendations
    for param, rec in report['recommended_parameters'].items():
        print(f"{param}: {rec}")
    
    # Parameters to test in shadow mode
    print("Shadow test candidates:")
    for candidate in report['shadow_test_candidates']:
        print(f"  - {candidate}")
```

### 3. Shadow Mode (`modules/shadow_calculator.py`)

Test new parameters without real trading:

```python
from modules.shadow_calculator import get_shadow_calculator

shadow = get_shadow_calculator()

# Create shadow scenario
scenario = shadow.create_shadow_scenario(
    scenario_name='tighter_stoploss',
    base_parameters={'stop_loss_percent': 0.5},
    modified_parameters={'stop_loss_percent': 0.3},
    description='Test tighter stop loss'
)

# Run shadow calculation
shadow.start_shadow_calculation(
    scenario=scenario,
    market_data={'current_price': 45000, 'high': 45500, 'low': 44800},
    signal_data={'direction': 'LONG', 'confidence_score': 80}
)

# Compare to live results later
comparison = shadow.compare_shadow_to_live(
    shadow_scenario_id=scenario['scenario_id'],
    live_trade_result={'actual_pnl_percent': 1.5}
)
```

### 4. Confidence System (`modules/confidence_system.py`)

Trust-score based confidence calculation:

```python
from modules.confidence_system import get_confidence_system

confidence = get_confidence_system()

# Calculate combined confidence
result = confidence.calculate_combined_confidence(
    indicator_signals={'rsi': {'strength': 0.8, 'direction': 1}},
    probability_field_result={'final_probability': 0.75},
    market_conditions={'atr_percent': 1.2, 'volume_ratio': 1.5}
)

print(f"Combined confidence: {result['combined_confidence_score']}%")
print(f"Can trade: {result['can_trade']}")
print(f"Recommendation: {result['recommendation']}")
```

### 5. Risk Management (`modules/risk_manager.py`)

Comprehensive risk controls:

```python
from modules.risk_manager import get_risk_manager

risk = get_risk_manager()

# Assess trade risk
assessment = risk.assess_trade_risk(trade_setup, current_balance=10000)

if assessment['decision'] == 'APPROVE':
    print("Trade approved")
elif assessment['decision'] == 'REJECT':
    print(f"Trade rejected: {assessment['risks']}")
else:
    print(f"Proceed with caution: {assessment['warnings']}")

# Get risk summary
summary = risk.get_risk_summary()
print(f"Daily PnL: {summary['daily_performance']['pnl']}")
print(f"Current drawdown: {summary['drawdown']['current']}%")
```

## Configuration

Edit `config/config.ini` to customize:

```ini
[LOGGING]
LOG_LEVEL = DEBUG
DETAILED_TRADE_LOG = True
LOG_SHADOW = True
AUTO_TUNE_ENABLED = True
AUTO_TUNE_INTERVAL = 60

[AUTOTUNE]
MIN_TRADES_FOR_TUNE = 50
TUNABLE_PARAMETERS = 
    confidence_threshold,
    stop_loss_percent,
    take_profit_percent,
    min_risk_reward

[RISK]
MAX_DAILY_LOSS = 5.0
STOP_LOSS_PERCENT = 0.5
TAKE_PROFIT_PERCENT = 1.0
MIN_RISK_REWARD = 1.5

[CONFIDENCE]
MIN_CONFIDENCE_SCORE = 75
CONFIDENCE_DECAY = 5.0
```

## Log Files

### trades.jsonl
Detailed trade information in JSON Lines format:
```json
{"timestamp": "2024-01-01T10:00:00", "event_type": "TRADE_OPENED", "trade_id": "...", ...}
{"timestamp": "2024-01-01T10:30:00", "event_type": "TRADE_CLOSED", "trade_id": "...", ...}
```

### decisions.jsonl
All trading decisions with reasoning:
```json
{"timestamp": "...", "decision": "OPEN", "reason": "...", "forbidden_reason": null, ...}
```

### shadow_calculations.jsonl
Shadow mode results and comparisons:
```json
{"timestamp": "...", "shadow_id": "...", "hypothetical_result": {...}, ...}
```

## Usage Example

```python
from modules.logger import get_logger
from modules.autotuner import get_autotuner
from modules.shadow_calculator import get_shadow_calculator
from modules.confidence_system import get_confidence_system
from modules.risk_manager import get_risk_manager
from modules.trade_calculator import get_trade_calculator

# Initialize all components
logger = get_logger()
autotuner = get_autotuner()
shadow = get_shadow_calculator()
confidence = get_confidence_system()
risk = get_risk_manager()
calculator = get_trade_calculator()

# Set up cross-references
confidence.set_logger(logger)
risk.set_logger(logger)
calculator.set_logger(logger)
shadow.set_logger(logger)

# Process a signal
signal = {'symbol': 'BTCUSDT', 'direction': 'LONG', 'confidence_score': 80}
logger.log_signal(signal)

# Calculate confidence
conf_result = confidence.calculate_combined_confidence(...)
logger.log_decision({'decision': 'OPEN' if conf_result['can_trade'] else 'SKIP', ...})

# If trade allowed, calculate setup
if conf_result['can_trade']:
    trade_setup = calculator.calculate_complete_trade(...)
    
    # Check risk
    risk_assessment = risk.assess_trade_risk(trade_setup, balance)
    
    if risk_assessment['decision'] == 'APPROVE':
        # Execute trade (using trade_executor)
        pass
    
    # Start shadow calculation with alternative parameters
    shadow_scenario = shadow.create_shadow_scenario(...)
    shadow.start_shadow_calculation(shadow_scenario, market_data, signal)

# Periodically run auto-tune
autotune_result = autotuner.run_autotune_analysis(logger)
```

## License

MIT License
