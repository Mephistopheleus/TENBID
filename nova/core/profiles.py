"""Runtime parameter profile contracts.

`base.ini` is a bootstrap/system config. `active_profile.json` is the working
profile owned by Autotuner/ProfileManager after the initial seed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class ParameterProfile:
    profile_id: str
    symbol: str
    profile_source: str
    autotuner_managed: bool
    values: Dict[str, Any]

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "ParameterProfile":
        required = ["profile_id", "symbol", "profile_source", "autotuner_managed"]
        missing = [key for key in required if key not in raw]
        if missing:
            raise ValueError(f"Profile is missing required keys: {missing}")

        values = {key: value for key, value in raw.items() if key not in required}
        return cls(
            profile_id=str(raw["profile_id"]),
            symbol=str(raw["symbol"]),
            profile_source=str(raw["profile_source"]),
            autotuner_managed=bool(raw["autotuner_managed"]),
            values=values,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "symbol": self.symbol,
            "profile_source": self.profile_source,
            "autotuner_managed": self.autotuner_managed,
            **self.values,
        }

