# TENBID Configuration
# Binance Testnet Settings

BINANCE_TESTNET_API_KEY = "mYVqkHL4mSwEiHrHC6PaurPUHOV7auYwXXpkSmMX7hSSY8KT7teRmbQV6BY9YD3i"
BINANCE_TESTNET_SECRET_KEY = "ym3B6HkI6ervEsc4We0jr47O51tueW8CRTqpU6TxbpwzKsxAtLWtGKtbeUQ86aBf"
BINANCE_TESTNET_URL = "https://testnet.binance.vision"

# Trading Parameters
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_TIMEFRAME = "1m"  # Scalping timeframe
MAX_POSITION_SIZE = 1000  # USDT
STOP_LOSS_PERCENT = 0.5  # %
TAKE_PROFIT_PERCENT = 1.0  # %

# Confidence System
MIN_CONFIDENCE_SCORE = 70  # Minimum score to execute trade
MAX_CONFIDENCE_SCORE = 100

# Risk Management
MAX_DAILY_LOSS = 5.0  # % of capital
MAX_DRAWDOWN = 0.0  # Target: 0%
TARGET_WINRATE = 100.0  # Target: 100%
TARGET_DAILY_PNL = 50.0  # Target: 50% per day

# Shadow Calculation
SHADOW_MODE_ENABLED = True
SHADOW_UPDATE_INTERVAL = 1  # seconds

# Mode: "testnet" or "live"
TRADING_MODE = "testnet"
