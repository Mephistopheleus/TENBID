"""Resolve ambiguous stop/target order with lower-timeframe candles.

The resolver is conservative: it only returns a resolved path when the
lower-timeframe sequence clearly touches one boundary before the other.
Otherwise the caller must keep the scenario ambiguous/unresolved.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from nova.data.models import Candle
from nova.shadow.outcome import OutcomeResult, ResolutionMethod


@dataclass(frozen=True)
class IntrabarResolution:
    resolved: bool
    result: str | None = None
    resolution_method: str | None = None
    exit_price: float | None = None
    candle_count: int = 0
    mfe_pct: float = 0.0
    mae_pct: float = 0.0
    reason: str = ""


class IntrabarResolver:
    def resolve_with_candles(
        self,
        *,
        candles: Iterable[Candle],
        entry: float,
        stop: float,
        target: float,
        direction: str,
    ) -> IntrabarResolution:
        candle_list = [candle for candle in candles if candle.is_closed]
        if not candle_list:
            return IntrabarResolution(False, reason="missing_lower_timeframe_candles")
        mfe_pct = 0.0
        mae_pct = 0.0
        for idx, candle in enumerate(candle_list, start=1):
            if direction == "LONG":
                mfe_pct = max(mfe_pct, (candle.high - entry) / entry * 100.0)
                mae_pct = min(mae_pct, (candle.low - entry) / entry * 100.0)
                hit_target = candle.high >= target
                hit_stop = candle.low <= stop
            else:
                mfe_pct = max(mfe_pct, (entry - candle.low) / entry * 100.0)
                mae_pct = min(mae_pct, (entry - candle.high) / entry * 100.0)
                hit_target = candle.low <= target
                hit_stop = candle.high >= stop

            if hit_target and hit_stop:
                return IntrabarResolution(
                    False,
                    candle_count=idx,
                    mfe_pct=mfe_pct,
                    mae_pct=mae_pct,
                    reason="lower_timeframe_candle_still_ambiguous",
                )
            if hit_target:
                return IntrabarResolution(
                    True,
                    result=OutcomeResult.OBSERVED_WIN,
                    resolution_method=ResolutionMethod.ONE_MINUTE_REPLAY,
                    exit_price=target,
                    candle_count=idx,
                    mfe_pct=mfe_pct,
                    mae_pct=mae_pct,
                    reason="target_touched_before_stop_on_lower_timeframe",
                )
            if hit_stop:
                return IntrabarResolution(
                    True,
                    result=OutcomeResult.OBSERVED_LOSS,
                    resolution_method=ResolutionMethod.ONE_MINUTE_REPLAY,
                    exit_price=stop,
                    candle_count=idx,
                    mfe_pct=mfe_pct,
                    mae_pct=mae_pct,
                    reason="stop_touched_before_target_on_lower_timeframe",
                )

        return IntrabarResolution(
            False,
            candle_count=len(candle_list),
            mfe_pct=mfe_pct,
            mae_pct=mae_pct,
            reason="no_boundary_touched_on_lower_timeframe",
        )
