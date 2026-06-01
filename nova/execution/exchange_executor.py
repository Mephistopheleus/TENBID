"""Exchange executor for TESTNET order attempts.

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
                testnet_only=self.config.trading_mode == "TESTNET",
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

    def _connector(self) -> BinanceFuturesConnector:
        section = "BINANCE_TESTNET" if self.config.trading_mode == "TESTNET" else "BINANCE_LIVE"
        base_url = self.config.secrets.get(section, "base_url", fallback=self.config.public_rest_base_url)
        if self.config.trading_mode == "TESTNET" and "binance.vision" in base_url:
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
    def _float_or_none(value: object) -> Optional[float]:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_raw(raw: dict[str, object]) -> dict[str, object]:
        return {key: value for key, value in raw.items() if key not in {"apiKey", "signature"}}
