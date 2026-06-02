"""Exchange executor for Binance Futures order attempts.

Executor is the physical edge. It does not decide, tune or manage risk.
"""

from __future__ import annotations

import json
from typing import Optional

from nova.core.config_loader import RuntimeConfig
from nova.decision.trade_plan import TradePlan
from nova.execution.binance_futures_connector import BinanceFuturesConnector, BinanceFuturesConnectorConfig
from nova.execution.models import ExecutionAttempt, ExecutorRequest, ExecutorResult, ExecutorResultStatus
from nova.risk.models import RiskDecision


class ExchangeExecutor:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config

    def execute(self, trade_plan: TradePlan, risk_decision: RiskDecision) -> ExecutionAttempt:
        if not risk_decision.approved_for_executor:
            result = ExecutorResult(
                request_id=None,
                plan_id=trade_plan.plan_id,
                status=ExecutorResultStatus.NOT_CALLED,
                reason="risk_decision_not_approved_for_executor",
                raw_response={"risk_status": risk_decision.status, "hard_blocks": risk_decision.hard_blocks},
            )
            return ExecutionAttempt(request=None, result=result)

        side = self._side_from_plan(trade_plan)
        if side is None:
            result = ExecutorResult(
                request_id=None,
                plan_id=trade_plan.plan_id,
                status=ExecutorResultStatus.NOT_CALLED,
                reason="trade_plan_has_no_executor_side",
                raw_response={"decision": trade_plan.decision},
            )
            return ExecutionAttempt(request=None, result=result)

        connector = self._connector()
        notional_usdt = self._notional_usdt(risk_decision.adjusted_size_factor)
        request: ExecutorRequest | None = None
        try:
            order = connector.prepare_market_order(
                symbol=trade_plan.symbol,
                side=side,
                notional_usdt=notional_usdt,
                mark_price=trade_plan.entry_price,
            )
            request = ExecutorRequest(
                plan_id=trade_plan.plan_id,
                risk_decision_id=risk_decision.risk_decision_id,
                symbol=trade_plan.symbol,
                side=side,
                order_type="MARKET",
                quantity=str(order["quantity"]),
                notional_usdt=float(order["notional_usdt"]),
                reference_price=float(order["mark_price"]),
                execution_connection=self.config.execution_connection,
                testnet_only=self.config.execution_connection == "BINANCE_TESTNET",
                reduce_only=False,
                payload={
                    "filters": order.get("filters", {}),
                    "requested_notional_usdt": notional_usdt,
                    "plan_entry_price": trade_plan.entry_price,
                },
            )
            raw = connector.place_order(order)
            result = ExecutorResult(
                request_id=request.request_id,
                plan_id=trade_plan.plan_id,
                status=ExecutorResultStatus.ACCEPTED,
                reason="binance_order_accepted",
                exchange_order_id=str(raw.get("orderId")) if raw.get("orderId") is not None else None,
                client_order_id=raw.get("clientOrderId"),
                executed_qty=self._float_or_none(raw.get("executedQty") or raw.get("origQty")),
                avg_price=self._float_or_none(raw.get("avgPrice")),
                raw_response=self._safe_raw(raw),
            )
            return ExecutionAttempt(request=request, result=result)
        except Exception as exc:  # noqa: BLE001 - executor must record exact exchange/preparation failure.
            reason = "executor_error"
            raw_response: dict[str, object] = {"error": str(exc)}
            try:
                parsed = json.loads(str(exc))
                if isinstance(parsed, dict):
                    raw_response = parsed
                    reason = str(parsed.get("msg") or parsed.get("code") or reason)
            except json.JSONDecodeError:
                pass
            result = ExecutorResult(
                request_id=request.request_id if request else None,
                plan_id=trade_plan.plan_id,
                status=ExecutorResultStatus.ERROR,
                reason=reason,
                raw_response=raw_response,
            )
            return ExecutionAttempt(request=request, result=result)

    def close_reduce_only(
        self,
        *,
        trade_plan: TradePlan,
        entry_attempt: ExecutionAttempt,
        risk_decision: RiskDecision,
    ) -> ExecutionAttempt:
        if entry_attempt.result.status != ExecutorResultStatus.ACCEPTED:
            result = ExecutorResult(
                request_id=None,
                plan_id=trade_plan.plan_id,
                status=ExecutorResultStatus.NOT_CALLED,
                reason="entry_order_not_accepted_for_close",
                raw_response={"entry_status": entry_attempt.result.status},
            )
            return ExecutionAttempt(request=None, result=result)
        close_side = self._opposite_side(self._side_from_plan(trade_plan))
        quantity = entry_attempt.result.executed_qty
        if close_side is None or quantity is None or quantity <= 0:
            result = ExecutorResult(
                request_id=None,
                plan_id=trade_plan.plan_id,
                status=ExecutorResultStatus.NOT_CALLED,
                reason="missing_close_side_or_quantity",
                raw_response={"close_side": close_side, "executed_qty": quantity},
            )
            return ExecutionAttempt(request=None, result=result)

        reference_price = trade_plan.entry_price or entry_attempt.result.avg_price or 0.0
        request = ExecutorRequest(
            plan_id=trade_plan.plan_id,
            risk_decision_id=risk_decision.risk_decision_id,
            symbol=trade_plan.symbol,
            side=close_side,
            order_type="MARKET",
            quantity=str(quantity),
            notional_usdt=float(quantity) * float(reference_price or 0.0),
            reference_price=float(reference_price or 0.0),
            execution_connection=self.config.execution_connection,
            testnet_only=self.config.execution_connection == "BINANCE_TESTNET",
            reduce_only=True,
            payload={
                "entry_result_id": entry_attempt.result.result_id,
                "entry_exchange_order_id": entry_attempt.result.exchange_order_id,
                "purpose": "exchange_position_close",
            },
        )
        order = {
            "symbol": trade_plan.symbol.upper(),
            "side": close_side,
            "type": "MARKET",
            "quantity": str(quantity),
            "reduceOnly": True,
        }
        try:
            raw = self._connector().place_order(order)
            result = ExecutorResult(
                request_id=request.request_id,
                plan_id=trade_plan.plan_id,
                status=ExecutorResultStatus.ACCEPTED,
                reason="binance_reduce_only_close_accepted",
                exchange_order_id=str(raw.get("orderId")) if raw.get("orderId") is not None else None,
                client_order_id=raw.get("clientOrderId"),
                executed_qty=self._float_or_none(raw.get("executedQty") or raw.get("origQty")),
                avg_price=self._float_or_none(raw.get("avgPrice")),
                raw_response=self._safe_raw(raw),
            )
            return ExecutionAttempt(request=request, result=result)
        except Exception as exc:  # noqa: BLE001 - close attempts must be recorded, not hidden.
            reason = "reduce_only_close_error"
            raw_response: dict[str, object] = {"error": str(exc)}
            try:
                parsed = json.loads(str(exc))
                if isinstance(parsed, dict):
                    raw_response = parsed
                    reason = str(parsed.get("msg") or parsed.get("code") or reason)
            except json.JSONDecodeError:
                pass
            result = ExecutorResult(
                request_id=request.request_id,
                plan_id=trade_plan.plan_id,
                status=ExecutorResultStatus.ERROR,
                reason=reason,
                raw_response=raw_response,
            )
            return ExecutionAttempt(request=request, result=result)

    def _connector(self) -> BinanceFuturesConnector:
        return self.connector()

    def connector(self) -> BinanceFuturesConnector:
        section = self.config.execution_connection
        base_url = self.config.secrets.get(section, "base_url", fallback=self.config.public_rest_base_url)
        if section == "BINANCE_TESTNET" and "binance.vision" in base_url:
            base_url = self.config.public_rest_base_url
        api_key = self.config.secrets.get(section, "api_key", fallback="")
        secret_key = self.config.secrets.get(section, "secret_key", fallback="")
        if not api_key or not secret_key:
            raise ValueError(f"missing_{section.lower()}_credentials")
        return BinanceFuturesConnector(
            BinanceFuturesConnectorConfig(
                base_url=base_url,
                api_key=api_key,
                secret_key=secret_key,
                timeout_sec=self.config.rest_timeout_sec,
            )
        )

    def close_request_from_position(
        self,
        *,
        plan: TradePlan,
        risk_decision: RiskDecision,
        position_side: str,
        quantity: float,
        reference_price: float,
        reason: str,
    ) -> ExecutorRequest:
        return ExecutorRequest(
            plan_id=plan.plan_id,
            risk_decision_id=risk_decision.risk_decision_id,
            symbol=plan.symbol,
            side=position_side,
            order_type="MARKET",
            quantity=str(quantity),
            notional_usdt=float(quantity) * float(reference_price or 0.0),
            reference_price=float(reference_price or 0.0),
            execution_connection=self.config.execution_connection,
            testnet_only=self.config.execution_connection == "BINANCE_TESTNET",
            reduce_only=True,
            payload={"purpose": "position_manager_close", "reason": reason},
        )

    def _notional_usdt(self, adjusted_size_factor: float) -> float:
        fraction = float(self.config.profile.values.get("testnet_order_notional_fraction", 0.20))
        cap = float(self.config.profile.values.get("testnet_order_notional_cap_usdt", 10.0))
        raw = self.config.initial_balance_usdt * max(0.0, fraction) * max(0.0, adjusted_size_factor)
        return max(0.0, min(raw, cap))

    @staticmethod
    def _side_from_plan(plan: TradePlan) -> Optional[str]:
        if plan.decision == "PREPARE_LONG":
            return "BUY"
        if plan.decision == "PREPARE_SHORT":
            return "SELL"
        return None

    @staticmethod
    def _opposite_side(side: Optional[str]) -> Optional[str]:
        if side == "BUY":
            return "SELL"
        if side == "SELL":
            return "BUY"
        return None

    @staticmethod
    def _float_or_none(value: object) -> Optional[float]:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def safe_raw(raw: dict[str, object]) -> dict[str, object]:
        return {key: value for key, value in raw.items() if key not in {"apiKey", "signature"}}

    @staticmethod
    def _safe_raw(raw: dict[str, object]) -> dict[str, object]:
        return ExchangeExecutor.safe_raw(raw)
