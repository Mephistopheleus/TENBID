"""Active profile reader.

All tunable working parameters must flow through this store instead of hardcoded constants.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


class ParameterStore:
    def __init__(self, profile_path: str = "config/active_profile.json") -> None:
        self.profile_path = Path(profile_path)

    def get_active_profile(self) -> Dict[str, Any]:
        with self.profile_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

