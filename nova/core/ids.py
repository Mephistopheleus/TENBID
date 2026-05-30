"""Stable ID helpers for tracing every decision and result."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


def new_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{prefix}_{stamp}_{uuid4().hex[:8]}"


RUN = "RUN"
CYCLE = "CYCLE"
EVENT = "EVENT"
SNAPSHOT = "SNAPSHOT"
ANALYSIS = "ANALYSIS"
CARD = "CARD"
FORECAST = "FORECAST"
MATRIX = "MATRIX"
PLAN = "PLAN"
SCENARIO = "SCENARIO"
OUTCOME = "OUTCOME"
PROFILE = "PROFILE"
RECOMMENDATION = "RECOMMENDATION"
