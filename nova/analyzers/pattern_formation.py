"""Canonical NOVA pattern/formations analyzer."""

from __future__ import annotations

from nova.analyzers.common import build_package, clamp, evidence_refs_for_snapshot, no_data_package, ordered_candles, safe_div
from nova.analyzers.contracts import AnalysisPackage, AnalyzerContext, AnalyzerManifest
from nova.core.evidence import CardType
from nova.data.synthetic_tf import timeframe_to_minutes


class PatternFormationAnalyzer:
    manifest = AnalyzerManifest(
        name="pattern_formation_analyzer",
        version="0.1.0",
        description="Observes candlestick and chart formations as structural hypotheses.",
        dependency_group="pattern_ohlcv_structure",
        required_inputs=["MarketSnapshot.candles"],
        supported_timeframes=["5m"],
        output_card_types=[CardType.FORECAST, CardType.STATE],
        parameter_names=["pattern_lookback_candles", "pattern_horizon_bars"],
    )

    def analyze(self, context: AnalyzerContext) -> AnalysisPackage:
        snapshot = context.market_snapshot
        if snapshot is None:
            return no_data_package(self.manifest, context, "missing_market_snapshot")
        series = snapshot.candle_series(context.timeframe, context.symbol)
        if series is None or series.count < 20:
            return no_data_package(self.manifest, context, "insufficient_candles")
        lookback = max(20, int(context.parameters.get("pattern_lookback_candles", 80)))
        horizon_bars = max(1, int(context.parameters.get("pattern_horizon_bars", 5)))
        candles = ordered_candles(series, lookback)
        candle_patterns = self._candlestick_patterns(candles)
        chart_patterns = self._chart_patterns(candles)
        if not candle_patterns and not chart_patterns:
            return no_data_package(self.manifest, context, "no_recognized_formations")
        latest = candles[-1].close
        local_low = min(item.low for item in candles[-20:])
        local_high = max(item.high for item in candles[-20:])
        formation_strength = clamp((len(candle_patterns) * 0.12) + (len(chart_patterns) * 0.22))
        width_pct = safe_div(local_high - local_low, latest, 0.0) * 100.0
        confidence = clamp(0.2 + formation_strength * 0.45 + min(width_pct / 4.0, 0.25), 0.1, 0.9)
        payload = {
            "phenomenon": "pattern_formation_hypotheses",
            "candlestick_patterns": candle_patterns,
            "chart_patterns": chart_patterns,
            "local_low": local_low,
            "local_high": local_high,
            "formation_strength": formation_strength,
            "donor_legacy_idea": "candles/chart_patterns_without_buy_sell_aggregation",
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
                    "price_low": local_low,
                    "price_high": local_high,
                    "horizon_min": horizon_min,
                    "probability": confidence,
                    "confidence": confidence,
                    "direction": "FORMATION_CONTEXT",
                    "phenomenon": "pattern_formation_hypotheses",
                    "field_shape": "formation_range",
                    "weight": 0.55,
                }
            ],
            state_type="pattern_formation_context",
            state_value=payload,
            ttl_sec=max(60, horizon_min * 60),
        )

    @staticmethod
    def _candlestick_patterns(candles) -> list[dict[str, float | str]]:
        patterns = []
        last = candles[-1]
        prev = candles[-2]
        body = abs(last.close - last.open)
        range_ = max(last.high - last.low, 0.00000001)
        upper = last.high - max(last.open, last.close)
        lower = min(last.open, last.close) - last.low
        if body / range_ <= 0.12:
            patterns.append({"name": "doji", "strength": 1.0 - body / range_})
        if lower >= body * 2.0 and upper <= body * 0.8:
            patterns.append({"name": "hammer_like_rejection", "strength": clamp(lower / range_)})
        if upper >= body * 2.0 and lower <= body * 0.8:
            patterns.append({"name": "shooting_star_like_rejection", "strength": clamp(upper / range_)})
        if last.close > last.open and prev.close < prev.open and last.close >= prev.open and last.open <= prev.close:
            patterns.append({"name": "bullish_engulfing_shape", "strength": clamp(body / range_)})
        if last.close < last.open and prev.close > prev.open and last.open >= prev.close and last.close <= prev.open:
            patterns.append({"name": "bearish_engulfing_shape", "strength": clamp(body / range_)})
        if last.high <= prev.high and last.low >= prev.low:
            patterns.append({"name": "inside_bar_compression", "strength": clamp(1.0 - range_ / max(prev.high - prev.low, 0.00000001))})
        if last.high >= prev.high and last.low <= prev.low:
            patterns.append({"name": "outside_bar_expansion", "strength": clamp(range_ / max(prev.high - prev.low, 0.00000001) - 1.0)})
        return patterns

    @staticmethod
    def _chart_patterns(candles) -> list[dict[str, float | str]]:
        recent = candles[-30:]
        highs = sorted((item.high for item in recent), reverse=True)[:3]
        lows = sorted(item.low for item in recent)[:3]
        close = recent[-1].close
        patterns = []
        if len(highs) >= 2 and abs(highs[0] - highs[1]) / close <= 0.004:
            patterns.append({"name": "double_top_zone", "level": (highs[0] + highs[1]) / 2.0})
        if len(lows) >= 2 and abs(lows[0] - lows[1]) / close <= 0.004:
            patterns.append({"name": "double_bottom_zone", "level": (lows[0] + lows[1]) / 2.0})
        first_range = max(item.high for item in recent[:10]) - min(item.low for item in recent[:10])
        last_range = max(item.high for item in recent[-10:]) - min(item.low for item in recent[-10:])
        if last_range < first_range * 0.65:
            patterns.append({"name": "range_compression", "compression_ratio": safe_div(last_range, first_range, 0.0)})
        return patterns
