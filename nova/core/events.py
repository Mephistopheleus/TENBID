"""Event contracts for append-only system memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from nova.core.ids import EVENT, new_id


@dataclass(frozen=True)
class Event:
    event_type: str
    payload: Dict[str, Any]
    event_id: str = field(default_factory=lambda: new_id(EVENT))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    run_id: Optional[str] = None
    cycle_id: Optional[str] = None
    source: Optional[str] = None


class EventTypes:
    SYSTEM_STARTED = "SYSTEM_STARTED"
    CONFIG_LOADED = "CONFIG_LOADED"
    PROFILE_APPLIED = "PROFILE_APPLIED"
    CYCLE_STARTED = "CYCLE_STARTED"
    DATA_WARMUP_STARTED = "DATA_WARMUP_STARTED"
    DATA_WARMUP_COMPLETED = "DATA_WARMUP_COMPLETED"
    DATA_WARMUP_FAILED = "DATA_WARMUP_FAILED"
    MARKET_SNAPSHOT_CREATED = "MARKET_SNAPSHOT_CREATED"
    WS_KLINE_STREAM_STARTED = "WS_KLINE_STREAM_STARTED"
    WS_KLINE_STREAM_COMPLETED = "WS_KLINE_STREAM_COMPLETED"
    WS_KLINE_STREAM_FAILED = "WS_KLINE_STREAM_FAILED"
    WS_KLINE_LOOP_STARTED = "WS_KLINE_LOOP_STARTED"
    WS_KLINE_LOOP_STOPPED = "WS_KLINE_LOOP_STOPPED"
    STATE_SNAPSHOT_CREATED = "STATE_SNAPSHOT_CREATED"
    FORECAST_MATRIX_BUILT = "FORECAST_MATRIX_BUILT"
    STATE_MATRIX_BUILT = "STATE_MATRIX_BUILT"
    TRADE_PLAN_CREATED = "TRADE_PLAN_CREATED"
    SCENARIO_REQUESTED = "SCENARIO_REQUESTED"
    SCENARIO_OUTCOME_RECORDED = "SCENARIO_OUTCOME_RECORDED"
    AUTOTUNE_RECOMMENDATION_CREATED = "AUTOTUNE_RECOMMENDATION_CREATED"
