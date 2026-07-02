"""Runtime configuration loader for NOVA.

Loads immutable secrets/mode, bootstrap system settings and the Autotuner-owned
active profile as separate concerns.
"""

from __future__ import annotations

import configparser
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from nova.core.profiles import ParameterProfile


@dataclass(frozen=True)
class RuntimeConfig:
    root_dir: Path
    trading_mode: str
    execution_connection: str
    live_unlock: bool
    symbol: str
    initial_balance_usdt: float
    base_timeframe: str
    synthetic_timeframes: list[str]
    warmup_candles: int
    market_type: str
    public_rest_base_url: str
    public_ws_base_url: str
    rest_timeout_sec: float
    use_ws_klines: bool
    ws_kline_mode: str
    ws_startup_probe_messages: int
    ws_startup_probe_timeout_sec: float
    ws_loop_max_runtime_sec: float
    ws_loop_connection_timeout_sec: float
    ws_loop_max_reconnects: int
    ws_loop_reconnect_backoff_sec: float
    native_tf_reconcile_enabled: bool
    reconcile_enabled: bool
    reconcile_candles: int
    orderbook_mode: str
    orderbook_limit: int
    orderbook_ttl_sec: float
    reconcile_interval_sec: float
    cycle_interval_sec: float
    battle_mode: bool
    event_log_path: Path
    sqlite_path: Path
    secrets: configparser.ConfigParser
    base: configparser.ConfigParser
    profile: ParameterProfile


class ConfigLoader:
    def __init__(self, root_dir: str | Path = ".") -> None:
        self.root_dir = Path(root_dir).resolve()

    def load(self) -> RuntimeConfig:
        secrets = self._read_ini("config/secrets.ini")
        base = self._read_ini("config/base.ini")
        profile = self._read_profile("config/active_profile.json")

        legacy_mode = secrets.get("MODE", "trading_mode", fallback="TESTNET").upper()
        execution_connection = secrets.get("MODE", "execution_connection", fallback="").upper()
        if not execution_connection:
            execution_connection = "BINANCE_LIVE" if legacy_mode == "LIVE" else "BINANCE_TESTNET"
        live_unlock = secrets.getboolean("MODE", "live_unlock", fallback=False)
        symbol = base.get("GENERAL", "symbol", fallback=profile.symbol)

        return RuntimeConfig(
            root_dir=self.root_dir,
            trading_mode=legacy_mode,
            execution_connection=execution_connection,
            live_unlock=live_unlock,
            symbol=symbol,
            initial_balance_usdt=base.getfloat("GENERAL", "initial_balance_usdt"),
            base_timeframe=base.get("GENERAL", "base_timeframe", fallback="5m"),
            synthetic_timeframes=self._split_csv(base.get("GENERAL", "synthetic_timeframes", fallback="")),
            warmup_candles=base.getint("DATA", "warmup_candles", fallback=300),
            market_type=base.get("DATA", "market_type", fallback="USD_M_FUTURES"),
            public_rest_base_url=base.get("DATA", "public_rest_base_url", fallback="https://testnet.binancefuture.com"),
            public_ws_base_url=base.get("DATA", "public_ws_base_url", fallback="wss://stream.binancefuture.com/ws"),
            rest_timeout_sec=base.getfloat("DATA", "rest_timeout_sec", fallback=10.0),
            use_ws_klines=base.getboolean("DATA", "use_ws_klines", fallback=True),
            ws_kline_mode=base.get("DATA", "ws_kline_mode", fallback="loop_slice"),
            ws_startup_probe_messages=base.getint("DATA", "ws_startup_probe_messages", fallback=5),
            ws_startup_probe_timeout_sec=base.getfloat("DATA", "ws_startup_probe_timeout_sec", fallback=10.0),
            ws_loop_max_runtime_sec=base.getfloat("DATA", "ws_loop_max_runtime_sec", fallback=15.0),
            ws_loop_connection_timeout_sec=base.getfloat("DATA", "ws_loop_connection_timeout_sec", fallback=5.0),
            ws_loop_max_reconnects=base.getint("DATA", "ws_loop_max_reconnects", fallback=2),
            ws_loop_reconnect_backoff_sec=base.getfloat("DATA", "ws_loop_reconnect_backoff_sec", fallback=1.0),
            native_tf_reconcile_enabled=base.getboolean("DATA", "native_tf_reconcile_enabled", fallback=True),
            reconcile_enabled=base.getboolean("DATA", "reconcile_enabled", fallback=True),
            reconcile_candles=base.getint("DATA", "reconcile_candles", fallback=120),
            orderbook_mode=base.get("DATA", "orderbook_mode", fallback="on_demand_rate_limited"),
            orderbook_limit=base.getint("DATA", "orderbook_limit", fallback=20),
            orderbook_ttl_sec=base.getfloat("DATA", "orderbook_ttl_sec", fallback=10.0),
            reconcile_interval_sec=base.getfloat("DATA", "reconcile_interval_sec", fallback=60.0),
            cycle_interval_sec=base.getfloat("GENERAL", "cycle_interval_sec", fallback=0.0),
            battle_mode=base.getboolean("GENERAL", "battle_mode", fallback=False),
            event_log_path=self.root_dir / base.get("LOGGING", "event_log_path", fallback="logs/events.jsonl"),
            sqlite_path=self.root_dir / base.get("LOGGING", "sqlite_path", fallback="nova_history.db"),
            secrets=secrets,
            base=base,
            profile=profile,
        )

    def _read_ini(self, relative_path: str) -> configparser.ConfigParser:
        path = self.root_dir / relative_path
        if not path.exists():
            raise FileNotFoundError(path)
        parser = configparser.ConfigParser()
        parser.read(path, encoding="utf-8")
        return parser

    def _read_profile(self, relative_path: str) -> ParameterProfile:
        path = self.root_dir / relative_path
        if not path.exists():
            raise FileNotFoundError(path)
        raw: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return ParameterProfile.from_dict(raw)

    @staticmethod
    def _split_csv(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]
