"""Canonical NOVA BTC correlation/context analyzer."""

from __future__ import annotations

import math

from nova.analyzers.common import build_package, clamp, evidence_refs_for_snapshot, no_data_package, ordered_candles, safe_div
from nova.analyzers.contracts import AnalysisPackage, AnalyzerContext, AnalyzerManifest
from nova.core.evidence import CardType
from nova.data.synthetic_tf import timeframe_to_minutes


class BTCCorrelationAnalyzer:
    manifest = AnalyzerManifest(
        name="btc_correlation_analyzer",
        version="0.1.0",
        description="Observes BTC coupling, decoupling and lag context from related candles.",
        dependency_group="btc_related_ohlcv",
        required_inputs=["MarketSnapshot.candles", "MarketSnapshot.related_candles.BTCUSDT"],
        supported_timeframes=["5m"],
        output_card_types=[CardType.STATE, CardType.FORECAST],
        parameter_names=["btc_correlation_lookback_candles", "btc_correlation_horizon_bars"],
    )

    def analyze(self, context: AnalyzerContext) -> AnalysisPackage:
        snapshot = context.market_snapshot
        if snapshot is None:
            return no_data_package(self.manifest, context, "missing_market_snapshot")
        target = snapshot.candle_series(context.timeframe, context.symbol)
        btc = snapshot.candle_series(context.timeframe, "BTCUSDT")
        if target is None or target.count < 20:
            return no_data_package(self.manifest, context, "insufficient_target_candles")
        if btc is None or btc.count < 20:
            return no_data_package(self.manifest, context, "missing_btc_related_candles")
        lookback = max(20, int(context.parameters.get("btc_correlation_lookback_candles", 96)))
        horizon_bars = max(1, int(context.parameters.get("btc_correlation_horizon_bars", 6)))
        target_candles = ordered_candles(target, lookback)
        btc_candles = ordered_candles(btc, lookback)
        target_returns = self._returns(target_candles)
        btc_returns = self._returns(btc_candles)
        size = min(len(target_returns), len(btc_returns))
        if size < 12:
            return no_data_package(self.manifest, context, "insufficient_return_overlap")
        target_returns = target_returns[-size:]
        btc_returns = btc_returns[-size:]
        correlation = self._pearson(target_returns, btc_returns)
        lag_map = {lag: self._lagged_corr(target_returns, btc_returns, lag) for lag in [-2, -1, 0, 1, 2]}
        best_lag = max(lag_map, key=lambda lag: abs(lag_map[lag]))
        target_change = safe_div(target_candles[-1].close - target_candles[0].open, target_candles[0].open, 0.0) * 100.0
        btc_change = safe_div(btc_candles[-1].close - btc_candles[0].open, btc_candles[0].open, 0.0) * 100.0
        divergence = target_change - btc_change
        coupling = self._coupling(correlation, divergence)
        latest = target_candles[-1].close
        move_hint = abs(correlation) * abs(btc_change) / 100.0 * latest
        width = max(latest * 0.002, move_hint)
        confidence = clamp(0.2 + abs(correlation) * 0.45 + min(abs(divergence) / 3.0, 0.25) + (0.1 if abs(lag_map[best_lag]) > abs(correlation) else 0.0), 0.1, 0.9)
        payload = {
            "phenomenon": "btc_coupling_context",
            "correlation": correlation,
            "coupling_state": coupling,
            "lag_correlation_map": lag_map,
            "best_lag_bars": best_lag,
            "target_change_pct": target_change,
            "btc_change_pct": btc_change,
            "divergence_pct": divergence,
            "donor_legacy_idea": "BTC influence/lag/divergence_without_permission_signal",
        }
        horizon_min = horizon_bars * timeframe_to_minutes(context.timeframe)
        return build_package(
            manifest=self.manifest,
            context=context,
            payload=payload,
            confidence=confidence,
            quality=min(snapshot.quality.score, target.quality.score, btc.quality.score),
            evidence_refs=evidence_refs_for_snapshot(snapshot, series=target, extra=evidence_refs_for_snapshot(snapshot, series=btc)[1:]),
            forecast_specs=[
                {
                    "price_low": max(0.00000001, latest - width),
                    "price_high": latest + width,
                    "horizon_min": horizon_min,
                    "probability": confidence,
                    "confidence": confidence,
                    "direction": "BTC_CONTEXT",
                    "phenomenon": "btc_coupling_context",
                    "field_shape": "coupling_envelope",
                    "weight": 0.35,
                }
            ],
            state_type="btc_correlation_context",
            state_value=payload,
            ttl_sec=max(60, horizon_min * 60),
        )

    @staticmethod
    def _returns(candles) -> list[float]:
        return [safe_div(candles[index].close - candles[index - 1].close, candles[index - 1].close, 0.0) for index in range(1, len(candles))]

    @staticmethod
    def _pearson(left: list[float], right: list[float]) -> float:
        size = min(len(left), len(right))
        if size < 2:
            return 0.0
        left = left[-size:]
        right = right[-size:]
        lm = sum(left) / size
        rm = sum(right) / size
        covariance = sum((left[i] - lm) * (right[i] - rm) for i in range(size))
        lv = math.sqrt(sum((item - lm) ** 2 for item in left))
        rv = math.sqrt(sum((item - rm) ** 2 for item in right))
        return clamp(safe_div(covariance, lv * rv, 0.0), -1.0, 1.0)

    def _lagged_corr(self, target: list[float], btc: list[float], lag: int) -> float:
        if lag > 0:
            return self._pearson(target[lag:], btc[:-lag])
        if lag < 0:
            return self._pearson(target[:lag], btc[-lag:])
        return self._pearson(target, btc)

    @staticmethod
    def _coupling(correlation: float, divergence: float) -> str:
        if abs(correlation) >= 0.65 and abs(divergence) < 1.5:
            return "COUPLED"
        if abs(correlation) < 0.25:
            return "DECOUPLED"
        if abs(divergence) >= 2.0:
            return "DIVERGENT"
        return "PARTIAL_COUPLING"
