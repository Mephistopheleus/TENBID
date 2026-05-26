# TENBID v2.0 Configuration
# Environment: Binance Futures Testnet

EXCHANGE_CONFIG = {
    "exchange": "binance",
    "testnet": True,
    "api_key": "mYVqkHL4mSwEiHrHC6PaurPUHOV7auYwXXpkSmMX7hSSY8KT7teRmbQV6BY9YD3i",
    "secret_key": "ym3B6HkI6ervEsc4We0jr47O51tueW8CRTqpU6TxbpwzKsxAtLWtGKtbeUQ86aBf",
    "options": {
        "defaultType": "future",
        "adjustForTimeDifference": True
    }
}

TRADING_CONFIG = {
    "symbol": "BTC/USDT",
    "timeframe": "5m",
    "initial_balance": 50.0,  # USDT
    "leverage": 10,
    "max_positions": 3,
    "risk_per_trade": 0.02,  # 2% of balance
    "max_drawdown": 0.15,    # Stop trading if drawdown > 15%
}

SYSTEM_CONFIG = {
    "mode": "live",  # 'backtest', 'shadow', 'live'
    "data_lineage_enabled": True,
    "auto_tuner_enabled": True,
    "shadow_lab_enabled": True,
    "laboratory_enabled": True,
    "log_level": "INFO",
    "confidence_threshold": 0.65,  # Minimum confidence to open trade
}

NEWS_SOURCES = [
    "https://cryptopanic.com/feeds/api/news/?auth_token=demo&filter=hot",  # Demo token for test, replace if needed
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/"
]
