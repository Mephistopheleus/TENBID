"""Canonical NOVA volatility/regime analyzer."""

from __future__ import annotations

from nova.analyzers.common import build_package, clamp, evidence_refs_for_snapshot, no_data_package, ordered_candles, safe_div
from nova.analyzers.contracts import AnalysisPackage, AnalyzerContext, AnalyzerManifest
from nova.core.evidence import CardType
from nova.data.synthetic_tf import timeframe_to_minutes


class VolatilityRegimeAnalyzer:
    manifest = AnalyzerManifest(
        name="volatility_regime_analyzer",
        version="0.1.0",
        description="Observes ATR expansion/compression and directional regime without voting.",
        dependency_group="ohlcv_regime",
        required_inputs=["MarketSnapshot.candles"],
        supported_timeframes=["5m"],
        output_card_types=[CardType.STATE, CardType.FORECAST],
        parameter_names=["regime_lookback_candles", "regime_atr_period", "regime_horizon_bars"],
    )

    def analyze(self, context: AnalyzerContext) -> AnalysisPackage:
        snapshot = context.market_snapshot
        if snapshot is None:
            return no_data_package(self.manifest, context, "missing_market_snapshot")
        series = snapshot.candle_series(context.timeframe, context.symbol)
        if series is None or series.count < 30:
            return no_data_package(self.manifest, context, "insufficient_candles")
        lookback = max(30, int(context.parameters.get("regime_lookback_candles", 120)))
        period = max(5, int(context.parameters.get("regime_atr_period", 14)))
        horizon_bars = max(1, int(context.parameters.get("regime_horizon_bars", 6)))
        candles = ordered_candles(series, lookback)
        atr_values = self._atr_series(candles, period)
        if not atr_values:
            return no_data_package(self.manifest, context, "insufficient_atr_window")
        latest = candles[-1].close
        atr = atr_values[-1]
        atr_pct = safe_div(atr, latest, 0.0) * 100.0
        median_atr = sorted(atr_values)[len(atr_values) // 2]
        atr_ratio = safe_div(atr, median_atr, 1.0)
        short_ma = sum(item.close for item in candles[-9:]) / min(9, len(candles))
        long_ma = sum(item.close for item in candles[-21:]) / min(21, len(candles))
        trend_strength = safe_div(short_ma - long_ma, latest, 0.0) * 100.0
        recent_range = max(item.high for item in candles[-period:]) - min(item.low for item in candles[-period:])
        regime = self._regime(atr_ratio, trend_strength)
        confidence = clamp(0.25 + min(abs(trend_strength) / 1.5, 0.35) + min(abs(atr_ratio - 1.0), 1.0) * 0.25 + min(atr_pct / 2.5, 0.15), 0.1, 0.9)
        band = max(atr * 1.5, recent_range * 0.35)
        payload = {
            "phenomenon": "volatility_regime_state",
            "regime": regime,
            "atr": atr,
            "atr_pct": atr_pct,
            "atr_ratio_to_median": atr_ratio,
            "ma9": short_ma,
            "ma21": long_ma,
            "trend_strength_pct": trend_strength,
            "recent_range": recent_range,
            "donor_legacy_idea": "ADX/ATR/regime_labels_without_trade_signal",
        }
        horizon_min = horizon_bars * timeframe_to_minutes(context.timeframe)
        return build_package(
            manifest=self.manifest,
            context=context,
            payload=payload,
            confidence=confidence,
            quality=min(snapshot.quality.score, series.quality.score),
            evidence_refs=evidence_refs_for_snapshot(snapshot, series=series),
            forecast_specs=[
                {
                    "price_low": max(0.00000001, latest - band),
                    "price_high": latest + band,
                    "horizon_min": horizon_min,
                    "probability": confidence,
                    "confidence": confidence,
                    "direction": "REGIME_CONTEXT",
                    "phenomenon": "volatility_regime_state",
                    "field_shape": "atr_envelope",
                    "weight": 0.45,
                }
            ],
            state_type="volatility_regime_context",
            state_value=payload,
            state_severity="WARN" if regime == "HIGH_VOLATILITY" else "INFO",
            ttl_sec=max(60, horizon_min * 60),
        )

    @staticmethod
    def _atr_series(candles, period: int) -> list[float]:
        true_ranges = []
        for index, candle in enumerate(candles):
            previous_close = candles[index - 1].close if index else candle.close
            true_ranges.append(max(candle.high - candle.low, abs(candle.high - previous_close), abs(candle.low - previous_close)))
        return [sum(true_ranges[index - period + 1 : index + 1]) / period for index in range(period - 1, len(true_ranges))]

    @staticmethod
    def _regime(atr_ratio: float, trend_strength: float) -> str:
        if atr_ratio >= 1.65:
            return "HIGH_VOLATILITY"
        if abs(trend_strength) < 0.12 and atr_ratio < 1.15:
            return "RANGING"
        if trend_strength > 0.0:
            return "TREND_UP_CONTEXT"
        return "TREND_DOWN_CONTEXT"
