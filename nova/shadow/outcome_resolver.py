"""Resolve pending scenario outcomes from closed candles.

The resolver is intentionally conservative: it only creates a traceable outcome
when the candle path is clear enough from OHLC data. Ambiguous SL/TP hits stay
unresolved instead of becoming fake evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from nova.data.models import Candle, MarketSnapshot
from nova.shadow.intrabar_resolver import IntrabarResolver
from nova.shadow.outcome import OutcomeResult, ResolutionMethod, ScenarioOutcome


@dataclass(frozen=True)
class OutcomeResolution:
    original_outcome_id: str
    resolved: bool
    outcome: Optional[ScenarioOutcome] = None
    reason: str = ""


class ScenarioOutcomeResolver:
    def resolve_pending(self, pending: ScenarioOutcome, snapshot: MarketSnapshot | None) -> OutcomeResolution:
        if snapshot is None:
            return OutcomeResolution(pending.outcome_id, False, reason="missing_market_snapshot")
        payload = pending.payload
        symbol = str(payload.get("symbol") or snapshot.primary_symbol)
        series = snapshot.candle_series(snapshot.base_timeframe, symbol)
        if series is None or not series.candles:
            return OutcomeResolution(pending.outcome_id, False, reason="missing_candle_series")

        entry = self._float(payload.get("entry_price"))
        stop = self._float(payload.get("stop_loss"))
        target = self._float(payload.get("take_profit"))
        if entry is None or stop is None or target is None or entry <= 0:
            return OutcomeResolution(pending.outcome_id, False, reason="missing_plan_prices")

        direction = self._direction(entry, stop, target)
        if direction is None:
            return OutcomeResolution(pending.outcome_id, False, reason="unsupported_plan_direction")

        window = max(1, int(payload.get("evaluation_window_min") or payload.get("horizon_min") or 1))
        candles = [candle for candle in series.candles if candle.is_closed][-window:]
        if not candles:
            return OutcomeResolution(pending.outcome_id, False, reason="no_closed_candles")

        return self._resolve_path(
            pending=pending,
            candles=candles,
            entry=entry,
            stop=stop,
            target=target,
            direction=direction,
        )

    def _resolve_path(
        self,
        *,
        pending: ScenarioOutcome,
        candles: Iterable[Candle],
        entry: float,
        stop: float,
        target: float,
        direction: str,
    ) -> OutcomeResolution:
        candle_list = list(candles)
        mfe_pct = 0.0
        mae_pct = 0.0
        ambiguous = False
        for idx, candle in enumerate(candle_list, start=1):
            if direction == "LONG":
                mfe_pct = max(mfe_pct, (candle.high - entry) / entry * 100)
                mae_pct = min(mae_pct, (candle.low - entry) / entry * 100)
                hit_target = candle.high >= target
                hit_stop = candle.low <= stop
            else:
                mfe_pct = max(mfe_pct, (entry - candle.low) / entry * 100)
                mae_pct = min(mae_pct, (entry - candle.high) / entry * 100)
                hit_target = candle.low <= target
                hit_stop = candle.high >= stop

            if hit_target and hit_stop:
                lower_timeframe = pending.payload.get("intrabar_timeframe", "1m")
                lower_candles = pending.payload.get("intrabar_candles")
                if isinstance(lower_candles, list):
                    intrabar = IntrabarResolver().resolve_with_candles(
                        candles=[candle for candle in lower_candles if isinstance(candle, Candle)],
                        entry=entry,
                        stop=stop,
                        target=target,
                        direction=direction,
                    )
                    if intrabar.resolved and intrabar.result is not None and intrabar.exit_price is not None:
                        return self._resolved(
                            pending,
                            intrabar.result,
                            intrabar.exit_price,
                            entry,
                            intrabar.mfe_pct,
                            intrabar.mae_pct,
                            intrabar.candle_count,
                            resolution_method=intrabar.resolution_method or ResolutionMethod.ONE_MINUTE_REPLAY,
                            notes=f"Resolved by {lower_timeframe} intrabar replay: {intrabar.reason}",
                        )
                ambiguous = True
                break
            if hit_target:
                return self._resolved(pending, OutcomeResult.OBSERVED_WIN, target, entry, mfe_pct, mae_pct, idx)
            if hit_stop:
                return self._resolved(pending, OutcomeResult.OBSERVED_LOSS, stop, entry, mfe_pct, mae_pct, idx)

        if ambiguous:
            unresolved = self._copy_with(
                pending,
                result=OutcomeResult.UNRESOLVED,
                resolution_method=ResolutionMethod.AMBIGUOUS,
                quality=0.0,
                notes="Both stop and target were touched inside one candle; OHLC path is ambiguous.",
            )
            return OutcomeResolution(pending.outcome_id, True, outcome=unresolved, reason="ambiguous_ohlc_path")

        last_close = candle_list[-1].close
        pnl_pct = self._pnl_pct(entry, last_close, direction)
        result = OutcomeResult.OBSERVED_FLAT
        if pnl_pct > 0:
            result = OutcomeResult.OBSERVED_WIN
        elif pnl_pct < 0:
            result = OutcomeResult.OBSERVED_LOSS
        return OutcomeResolution(
            pending.outcome_id,
            True,
            outcome=ScenarioOutcome(
                scenario_id=pending.scenario_id,
                source_type=pending.source_type,
                result=result,
                gross_pnl_pct=pnl_pct,
                net_pnl_pct=pnl_pct - float(pending.planned_costs.get("total_cost_pct", 0.0)),
                mfe_pct=mfe_pct,
                mae_pct=mae_pct,
                duration_sec=len(candle_list) * 60,
                resolution_method=ResolutionMethod.OHLC_CLEAR,
                quality=0.7,
                planned_costs=pending.planned_costs,
                actual_costs={},
                payload={**pending.payload, "resolved_from_outcome_id": pending.outcome_id, "exit_price": last_close},
                notes="Evaluation window ended without SL/TP hit; resolved by final close.",
            ),
            reason="window_close_resolution",
        )

    def _resolved(
        self,
        pending: ScenarioOutcome,
        result: str,
        exit_price: float,
        entry: float,
        mfe_pct: float,
        mae_pct: float,
        candle_count: int,
        resolution_method: str = ResolutionMethod.OHLC_CLEAR,
        notes: str = "Resolved by clear OHLC stop/target hit.",
    ) -> OutcomeResolution:
        direction = self._direction(entry, self._float(pending.payload.get("stop_loss")), self._float(pending.payload.get("take_profit"))) or "LONG"
        gross_pnl = self._pnl_pct(entry, exit_price, direction)
        outcome = ScenarioOutcome(
            scenario_id=pending.scenario_id,
            source_type=pending.source_type,
            result=result,
            gross_pnl_pct=gross_pnl,
            net_pnl_pct=gross_pnl - float(pending.planned_costs.get("total_cost_pct", 0.0)),
            mfe_pct=mfe_pct,
            mae_pct=mae_pct,
            duration_sec=candle_count * 60,
            resolution_method=resolution_method,
            quality=1.0,
            planned_costs=pending.planned_costs,
            actual_costs={},
            payload={**pending.payload, "resolved_from_outcome_id": pending.outcome_id, "exit_price": exit_price},
            notes=notes,
        )
        return OutcomeResolution(pending.outcome_id, True, outcome=outcome, reason="clear_ohlc_hit")

    @staticmethod
    def _copy_with(pending: ScenarioOutcome, *, result: str, resolution_method: str, quality: float, notes: str) -> ScenarioOutcome:
        return ScenarioOutcome(
            scenario_id=pending.scenario_id,
            source_type=pending.source_type,
            result=result,
            gross_pnl_pct=0.0,
            net_pnl_pct=0.0,
            mfe_pct=pending.mfe_pct,
            mae_pct=pending.mae_pct,
            duration_sec=pending.duration_sec,
            resolution_method=resolution_method,
            quality=quality,
            planned_costs=pending.planned_costs,
            actual_costs=pending.actual_costs,
            payload={**pending.payload, "resolved_from_outcome_id": pending.outcome_id},
            notes=notes,
        )

    @staticmethod
    def _direction(entry: float, stop: float | None, target: float | None) -> Optional[str]:
        if stop is None or target is None:
            return None
        if stop < entry < target:
            return "LONG"
        if target < entry < stop:
            return "SHORT"
        return None

    @staticmethod
    def _pnl_pct(entry: float, exit_price: float, direction: str) -> float:
        if direction == "LONG":
            return (exit_price - entry) / entry * 100
        return (entry - exit_price) / entry * 100

    @staticmethod
    def _float(value: object) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
