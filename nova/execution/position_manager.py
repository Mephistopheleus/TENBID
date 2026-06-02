"""TESTNET/LIVE-like position lifecycle manager.

This module does not create scenarios and does not bypass RiskManager. It only
tracks the physical exchange position after an accepted entry and closes it by
the scenario's own boundaries: stop, target, invalidation/time horizon, or an
explicit emergency close.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from nova.core.config_loader import RuntimeConfig
from nova.core.history_db import HistoryDB
from nova.core.ids import new_id
from nova.decision.trade_plan import TradePlan
from nova.execution.binance_futures_connector import BinanceFuturesConnector
from nova.execution.exchange_executor import ExchangeExecutor
from nova.execution.models import ExecutionAttempt, ExecutorResult, ExecutorResultStatus
from nova.risk.models import RiskDecision


@dataclass(frozen=True)
class ExchangePosition:
    symbol: str
    position_amt: float
    entry_price: float
    mark_price: float
    unrealized_profit: float
    position_side: str = "BOTH"
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def direction(self) -> Optional[str]:
        if self.position_amt > 0:
            return "LONG"
        if self.position_amt < 0:
            return "SHORT"
        return None

    @property
    def quantity_abs(self) -> float:
        return abs(self.position_amt)


@dataclass(frozen=True)
class PositionManagementResult:
    status: str
    reason: str
    position: Optional[ExchangePosition] = None
    close_attempt: Optional[ExecutionAttempt] = None
    payload: dict[str, Any] = field(default_factory=dict)


class PositionManager:
    def __init__(
        self,
        config: RuntimeConfig,
        connector: BinanceFuturesConnector | None = None,
        history_db: HistoryDB | None = None,
    ) -> None:
        self.config = config
        self.connector = connector or ExchangeExecutor(config).connector()
        self.history_db = history_db

    def manage_after_entry(
        self,
        *,
        plan: TradePlan,
        entry_attempt: ExecutionAttempt,
        risk_decision: RiskDecision,
    ) -> PositionManagementResult:
        if entry_attempt.result.status != ExecutorResultStatus.ACCEPTED:
            return PositionManagementResult("NOT_CALLED", "entry_not_accepted")
        if not bool(self.config.profile.values.get("position_manager_enabled", True)):
            return PositionManagementResult("NOT_CALLED", "position_manager_disabled")

        settle_delay_sec = float(self.config.profile.values.get("position_entry_settle_delay_sec", 1.0))
        if settle_delay_sec > 0:
            time.sleep(settle_delay_sec)

        position = self.current_position(plan.symbol)
        if position is None:
            return PositionManagementResult(
                "NO_POSITION",
                "no_exchange_position_after_entry_ack",
                payload={"entry_result_id": entry_attempt.result.result_id},
            )

        close_reason = self._close_reason(plan, position)
        if close_reason is None:
            return PositionManagementResult(
                "OPEN",
                "position_open_within_scenario_boundaries",
                position=position,
                payload=self._position_payload(plan, position),
            )

        close_attempt = self.close_position(plan=plan, position=position, risk_decision=risk_decision, reason=close_reason)
        return PositionManagementResult(
            "CLOSE_ATTEMPTED",
            close_reason,
            position=position,
            close_attempt=close_attempt,
            payload=self._position_payload(plan, position),
        )

    def current_position(self, symbol: str) -> Optional[ExchangePosition]:
        positions = self.connector.get_position_risk(symbol)
        for raw in positions:
            amount = self._float(raw.get("positionAmt"))
            if amount is None or abs(amount) <= 0.0:
                continue
            return ExchangePosition(
                symbol=str(raw.get("symbol") or symbol).upper(),
                position_amt=amount,
                entry_price=self._float(raw.get("entryPrice")) or 0.0,
                mark_price=self._float(raw.get("markPrice")) or 0.0,
                unrealized_profit=self._float(raw.get("unRealizedProfit")) or 0.0,
                position_side=str(raw.get("positionSide") or "BOTH"),
                raw=dict(raw),
            )
        return None

    def close_position(
        self,
        *,
        plan: TradePlan,
        position: ExchangePosition,
        risk_decision: RiskDecision,
        reason: str,
    ) -> ExecutionAttempt:
        side = "SELL" if position.position_amt > 0 else "BUY"
        request = ExchangeExecutor(self.config).close_request_from_position(
            plan=plan,
            risk_decision=risk_decision,
            position_side=side,
            quantity=position.quantity_abs,
            reference_price=position.mark_price or position.entry_price,
            reason=reason,
        )
        try:
            raw = self.connector.place_reduce_only_market_order(
                symbol=plan.symbol,
                side=side,
                quantity=request.quantity,
            )
            result = ExecutorResult(
                request_id=request.request_id,
                plan_id=plan.plan_id,
                status=ExecutorResultStatus.ACCEPTED,
                reason="position_manager_reduce_only_close_accepted",
                exchange_order_id=str(raw.get("orderId")) if raw.get("orderId") is not None else None,
                client_order_id=raw.get("clientOrderId"),
                executed_qty=self._float(raw.get("executedQty") or raw.get("origQty")),
                avg_price=self._float(raw.get("avgPrice")),
                raw_response=ExchangeExecutor.safe_raw(raw),
            )
        except Exception as exc:  # noqa: BLE001 - physical close failures must be recorded exactly.
            result = ExecutorResult(
                request_id=request.request_id,
                plan_id=plan.plan_id,
                status=ExecutorResultStatus.ERROR,
                reason=str(exc),
                raw_response={"error": str(exc), "close_reason": reason},
            )
        return ExecutionAttempt(request=request, result=result)

    def register_open_position(self, *, plan: TradePlan, position: ExchangePosition, entry_attempt: ExecutionAttempt) -> dict[str, Any]:
        payload = {
            "position_id": new_id("POSITION"),
            "symbol": position.symbol,
            "status": "OPEN",
            "plan_id": plan.plan_id,
            "scenario_id": plan.dynamics_summary.get("scenario_id"),
            "side": position.direction or "UNKNOWN",
            "quantity": position.quantity_abs,
            "entry_price": position.entry_price or entry_attempt.result.avg_price or plan.entry_price or 0.0,
            "stop_loss": plan.stop_loss,
            "take_profit": plan.take_profit,
            "opened_at": utc_now(),
            "last_seen_at": utc_now(),
            "closed_at": None,
            "entry_result_id": entry_attempt.result.result_id,
            "entry_exchange_order_id": entry_attempt.result.exchange_order_id,
            "horizon_min": plan.dynamics_summary.get("horizon_min"),
            "trailing_activation_pct": plan.dynamics_summary.get("management_seed", {}).get("trailing_activation_pct")
            if isinstance(plan.dynamics_summary.get("management_seed"), dict)
            else None,
            "max_favorable_pct": 0.0,
            "max_adverse_pct": 0.0,
        }
        if self.history_db is not None:
            self.history_db.upsert_active_position(payload)
        return payload

    def manage_open_records(self, *, risk_decision: RiskDecision) -> list[PositionManagementResult]:
        if self.history_db is None:
            return []
        results: list[PositionManagementResult] = []
        for record in self.history_db.active_position_records(self.config.symbol):
            position = self.current_position(str(record["symbol"]))
            if position is None:
                self.history_db.mark_active_position_closed(
                    str(record["position_id"]),
                    closed_at=utc_now(),
                    payload_extra={"close_reason": "position_absent_on_exchange"},
                )
                results.append(PositionManagementResult("CLOSED_EXTERNALLY", "position_absent_on_exchange", payload=record))
                continue
            plan = self._plan_from_record(record)
            close_reason = self._close_reason(plan, position, opened_at=str(record.get("opened_at") or ""), record=record)
            updated = self._updated_record(record, plan, position)
            self.history_db.upsert_active_position(updated)
            if close_reason is None:
                results.append(PositionManagementResult("OPEN", "position_open_within_scenario_boundaries", position=position, payload=updated))
                continue
            close_attempt = self.close_position(plan=plan, position=position, risk_decision=risk_decision, reason=close_reason)
            if close_attempt.result.status == ExecutorResultStatus.ACCEPTED:
                self.history_db.mark_active_position_closed(
                    str(record["position_id"]),
                    closed_at=utc_now(),
                    payload_extra={"close_reason": close_reason, "close_result_id": close_attempt.result.result_id},
                )
            results.append(
                PositionManagementResult(
                    "CLOSE_ATTEMPTED",
                    close_reason,
                    position=position,
                    close_attempt=close_attempt,
                    payload=updated,
                )
            )
        return results

    def _close_reason(
        self,
        plan: TradePlan,
        position: ExchangePosition,
        *,
        opened_at: str | None = None,
        record: dict[str, Any] | None = None,
    ) -> Optional[str]:
        mark = position.mark_price
        if mark <= 0.0:
            return None
        if position.direction == "LONG":
            if plan.stop_loss is not None and mark <= plan.stop_loss:
                return "stop_loss_reached"
            if plan.take_profit is not None and mark >= plan.take_profit:
                return "take_profit_reached"
        if position.direction == "SHORT":
            if plan.stop_loss is not None and mark >= plan.stop_loss:
                return "stop_loss_reached"
            if plan.take_profit is not None and mark <= plan.take_profit:
                return "take_profit_reached"
        trailing_reason = self._trailing_close_reason(plan, position, record or {})
        if trailing_reason is not None:
            return trailing_reason
        if opened_at and self._horizon_expired(plan, opened_at):
            return "scenario_horizon_expired"
        return None

    def _trailing_close_reason(self, plan: TradePlan, position: ExchangePosition, record: dict[str, Any]) -> Optional[str]:
        activation = self._float(record.get("trailing_activation_pct"))
        if activation is None:
            management_seed = plan.dynamics_summary.get("management_seed")
            if isinstance(management_seed, dict):
                activation = self._float(management_seed.get("trailing_activation_pct"))
        if activation is None or activation <= 0.0:
            return None
        entry = position.entry_price or self._float(record.get("entry_price")) or plan.entry_price
        if entry is None or entry <= 0.0 or position.mark_price <= 0.0:
            return None
        if position.direction == "LONG":
            current = (position.mark_price - entry) / entry * 100.0
        elif position.direction == "SHORT":
            current = (entry - position.mark_price) / entry * 100.0
        else:
            return None
        max_favorable = max(current, self._float(record.get("max_favorable_pct")) or 0.0)
        trail_back_pct = float(self.config.profile.values.get("trailing_giveback_pct", activation / 2.0))
        if max_favorable >= activation and current <= max_favorable - trail_back_pct:
            return "trailing_giveback_reached"
        return None

    def _horizon_expired(self, plan: TradePlan, opened_at: str) -> bool:
        horizon_min = self._float(plan.dynamics_summary.get("horizon_min"))
        if horizon_min is None:
            return False
        multiplier = float(self.config.profile.values.get("position_max_horizon_multiplier", 1.0))
        try:
            opened = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        age_sec = (datetime.now(timezone.utc) - opened).total_seconds()
        return age_sec >= horizon_min * 60.0 * max(0.1, multiplier)

    def _updated_record(self, record: dict[str, Any], plan: TradePlan, position: ExchangePosition) -> dict[str, Any]:
        entry = position.entry_price or self._float(record.get("entry_price")) or plan.entry_price or 0.0
        current = 0.0
        if entry > 0.0 and position.mark_price > 0.0:
            if position.direction == "LONG":
                current = (position.mark_price - entry) / entry * 100.0
            elif position.direction == "SHORT":
                current = (entry - position.mark_price) / entry * 100.0
        updated = dict(record)
        updated["last_seen_at"] = utc_now()
        updated["mark_price"] = position.mark_price
        updated["unrealized_profit"] = position.unrealized_profit
        updated["max_favorable_pct"] = max(self._float(record.get("max_favorable_pct")) or 0.0, current)
        updated["max_adverse_pct"] = min(self._float(record.get("max_adverse_pct")) or 0.0, current)
        return updated

    @staticmethod
    def _plan_from_record(record: dict[str, Any]) -> TradePlan:
        side = str(record.get("side") or "UNKNOWN")
        decision = "PREPARE_LONG" if side == "LONG" else "PREPARE_SHORT"
        return TradePlan(
            decision=decision,
            symbol=str(record["symbol"]),
            reason="active_position_management_record",
            profile_id=str(record.get("profile_id") or "POSITION_MANAGER"),
            entry_price=PositionManager._float(record.get("entry_price")),
            stop_loss=PositionManager._float(record.get("stop_loss")),
            take_profit=PositionManager._float(record.get("take_profit")),
            dynamics_summary={
                "scenario_id": record.get("scenario_id"),
                "horizon_min": record.get("horizon_min"),
                "management_seed": {"trailing_activation_pct": record.get("trailing_activation_pct")},
            },
            plan_id=str(record["plan_id"]),
        )

    @staticmethod
    def _position_payload(plan: TradePlan, position: ExchangePosition) -> dict[str, Any]:
        return {
            "plan_id": plan.plan_id,
            "symbol": position.symbol,
            "direction": position.direction,
            "position_amt": position.position_amt,
            "entry_price": position.entry_price,
            "mark_price": position.mark_price,
            "unrealized_profit": position.unrealized_profit,
            "stop_loss": plan.stop_loss,
            "take_profit": plan.take_profit,
            "horizon_min": plan.dynamics_summary.get("horizon_min"),
        }

    @staticmethod
    def _float(value: object) -> Optional[float]:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
