"""Reconcile submitted exchange orders with Binance status/fill state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nova.execution.binance_futures_connector import BinanceFuturesConnector
from nova.execution.models import ExecutionAttempt, ExecutorResultStatus


@dataclass(frozen=True)
class OrderReconciliation:
    status: str
    plan_id: str
    executor_result_id: str
    exchange_order_id: str | None
    client_order_id: str | None
    order_status: str | None = None
    executed_qty: float | None = None
    avg_price: float | None = None
    raw_response: dict[str, object] = field(default_factory=dict)
    reason: str | None = None


class OrderTracker:
    def __init__(self, connector: BinanceFuturesConnector) -> None:
        self.connector = connector

    def reconcile_attempt(self, attempt: ExecutionAttempt) -> OrderReconciliation:
        result = attempt.result
        if result.status != ExecutorResultStatus.ACCEPTED:
            return OrderReconciliation(
                status="SKIPPED",
                plan_id=result.plan_id,
                executor_result_id=result.result_id,
                exchange_order_id=result.exchange_order_id,
                client_order_id=result.client_order_id,
                reason="executor_result_not_accepted",
            )
        if attempt.request is None:
            return OrderReconciliation(
                status="FAILED",
                plan_id=result.plan_id,
                executor_result_id=result.result_id,
                exchange_order_id=result.exchange_order_id,
                client_order_id=result.client_order_id,
                reason="missing_executor_request",
            )
        if result.exchange_order_id is None and result.client_order_id is None:
            return OrderReconciliation(
                status="FAILED",
                plan_id=result.plan_id,
                executor_result_id=result.result_id,
                exchange_order_id=result.exchange_order_id,
                client_order_id=result.client_order_id,
                reason="missing_exchange_order_reference",
            )
        try:
            raw = self.connector.get_order(
                symbol=attempt.request.symbol,
                order_id=result.exchange_order_id,
                orig_client_order_id=result.client_order_id,
            )
        except Exception as exc:  # noqa: BLE001 - reconciliation failure must be recorded, not hidden.
            return OrderReconciliation(
                status="FAILED",
                plan_id=result.plan_id,
                executor_result_id=result.result_id,
                exchange_order_id=result.exchange_order_id,
                client_order_id=result.client_order_id,
                reason=str(exc),
            )
        return OrderReconciliation(
            status="RECONCILED",
            plan_id=result.plan_id,
            executor_result_id=result.result_id,
            exchange_order_id=str(raw.get("orderId")) if raw.get("orderId") is not None else result.exchange_order_id,
            client_order_id=raw.get("clientOrderId") or result.client_order_id,
            order_status=str(raw.get("status")) if raw.get("status") is not None else None,
            executed_qty=self._float(raw.get("executedQty")),
            avg_price=self._float(raw.get("avgPrice")),
            raw_response=self._safe_raw(raw),
        )

    @staticmethod
    def _float(value: object) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_raw(raw: dict[str, Any]) -> dict[str, object]:
        return {key: value for key, value in raw.items() if key not in {"apiKey", "signature"}}
