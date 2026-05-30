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
    live_unlock: bool
    symbol: str
    initial_balance_usdt: float
    base_timeframe: str
    synthetic_timeframes: list[str]
    warmup_candles: int
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

        trading_mode = secrets.get("MODE", "trading_mode", fallback="TESTNET").upper()
        live_unlock = secrets.getboolean("MODE", "live_unlock", fallback=False)
        symbol = base.get("GENERAL", "symbol", fallback=profile.symbol)

        return RuntimeConfig(
            root_dir=self.root_dir,
            trading_mode=trading_mode,
            live_unlock=live_unlock,
            symbol=symbol,
            initial_balance_usdt=base.getfloat("GENERAL", "initial_balance_usdt"),
            base_timeframe=base.get("GENERAL", "base_timeframe", fallback="5m"),
            synthetic_timeframes=self._split_csv(base.get("GENERAL", "synthetic_timeframes", fallback="")),
            warmup_candles=base.getint("DATA", "warmup_candles", fallback=300),
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

