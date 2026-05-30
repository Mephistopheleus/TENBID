"""Append-only event log.

Persists every fact needed for replay, episode building and Autotuner evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

from nova.core.events import Event


class EventLog:
    def __init__(self, path: str = "logs/events.jsonl") -> None:
        self.path = Path(path)

    def append(self, event: Event) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event.__dict__, ensure_ascii=False, default=str) + "\n")

