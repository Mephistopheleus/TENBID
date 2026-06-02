"""Execution edge contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from nova.core.ids import new_id


class ExecutorResultStatus:
    NOT_CALLED = "NOT_CALLED"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ExecutorRequest:
    plan_id: str
    risk_decision_id: str
    symbol: str
    side: str
    order_type: str
    quantity: str
    notional_usdt: float
    reference_price: float
    execution_connection: str = "BINANCE_TESTNET"
    testnet_only: bool = True
    reduce_only: bool = False
    payload: Dict[str, object] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: new_id("EXEC_REQ"))


@dataclass(frozen=True)
class ExecutorResult:
    request_id: Optional[str]
    plan_id: str
    status: str
    reason: str
    exchange_order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    executed_qty: Optional[float] = None
    avg_price: Optional[float] = None
    raw_response: Dict[str, object] = field(default_factory=dict)
    result_id: str = field(default_factory=lambda: new_id("EXEC_RESULT"))


@dataclass(frozen=True)
class ExecutionAttempt:
    request: Optional[ExecutorRequest]
    result: ExecutorResult
