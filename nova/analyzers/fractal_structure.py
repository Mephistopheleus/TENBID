"""Canonical NOVA fractal/structure analyzer."""

from __future__ import annotations

from nova.analyzers.common import build_package, clamp, evidence_refs_for_snapshot, no_data_package, ordered_candles, safe_div
from nova.analyzers.contracts import AnalysisPackage, AnalyzerContext, AnalyzerManifest
from nova.core.evidence import CardType
from nova.data.synthetic_tf import timeframe_to_minutes


class FractalStructureAnalyzer:
    manifest = AnalyzerManifest(
        name="fractal_structure_analyzer",
        version="0.1.0",
        description="Observes Williams fractals, clusters and invalidation topology.",
        dependency_group="fractal_ohlcv_structure",
        required_inputs=["MarketSnapshot.candles"],
        supported_timeframes=["5m"],
        output_card_types=[CardType.FORECAST, CardType.STATE],
        parameter_names=["fractal_lookback_candles", "fractal_cluster_threshold_pct", "fractal_horizon_bars"],
    )

    def analyze(self, context: AnalyzerContext) -> AnalysisPackage:
        snapshot = context.market_snapshot
        if snapshot is None:
            return no_data_package(self.manifest, context, "missing_market_snapshot")
        series = snapshot.candle_series(context.timeframe, context.symbol)
        if series is None or series.count < 9:
            return no_data_package(self.manifest, context, "insufficient_candles")
        lookback = max(9, int(context.parameters.get("fractal_lookback_candles", 120)))
        threshold_pct = max(0.05, float(context.parameters.get("fractal_cluster_threshold_pct", 0.35)))
        horizon_bars = max(1, int(context.parameters.get("fractal_horizon_bars", 8)))
        candles = ordered_candles(series, lookback)
        highs, lows = self._fractals(candles)
        if not highs and not lows:
            return no_data_package(self.manifest, context, "no_confirmed_fractals")
        latest = candles[-1].close
        high_clusters = self._clusters(highs, latest, threshold_pct)
        low_clusters = self._clusters(lows, latest, threshold_pct)
        nearest_resistance = min((item["price"] for item in high_clusters if item["price"] >= latest), default=max(highs, default=latest))
        nearest_support = max((item["price"] for item in low_clusters if item["price"] <= latest), default=min(lows, default=latest))
        low = max(0.00000001, nearest_support)
        high = max(low, nearest_resistance)
        density = clamp((len(highs) + len(lows)) / max(1, len(candles)) * 3.0)
        cluster_strength = clamp((sum(item["count"] for item in high_clusters + low_clusters)) / max(1, len(highs) + len(lows)))
        confidence = clamp(0.25 + density * 0.25 + cluster_strength * 0.30 + min(safe_div(high - low, latest, 0.0) * 100.0 / 3.0, 0.20), 0.1, 0.9)
        payload = {
            "phenomenon": "confirmed_fractal_structure",
            "fractal_high_count": len(highs),
            "fractal_low_count": len(lows),
            "high_clusters": high_clusters[:8],
            "low_clusters": low_clusters[:8],
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
            "structure_width_pct": safe_div(high - low, latest, 0.0) * 100.0,
            "invalidation_candidates": {"below_support": nearest_support, "above_resistance": nearest_resistance},
            "donor_legacy_idea": "Williams_fractals/clusters_without_trend_signal",
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
                    "price_low": low,
                    "price_high": high,
                    "horizon_min": horizon_min,
                    "probability": confidence,
                    "confidence": confidence,
                    "direction": "FRACTAL_STRUCTURE_CONTEXT",
                    "phenomenon": "confirmed_fractal_structure",
                    "field_shape": "support_resistance_band",
                    "invalidation_price": nearest_support if latest >= (low + high) / 2.0 else nearest_resistance,
                }
            ],
            state_type="fractal_structure_context",
            state_value=payload,
            ttl_sec=max(60, horizon_min * 60),
        )

    @staticmethod
    def _fractals(candles) -> tuple[list[float], list[float]]:
        highs = []
        lows = []
        for index in range(2, len(candles) - 2):
            window = candles[index - 2 : index + 3]
            candle = candles[index]
            if candle.high == max(item.high for item in window) and sum(1 for item in window if item.high == candle.high) == 1:
                highs.append(candle.high)
            if candle.low == min(item.low for item in window) and sum(1 for item in window if item.low == candle.low) == 1:
                lows.append(candle.low)
        return highs, lows

    @staticmethod
    def _clusters(levels: list[float], reference: float, threshold_pct: float) -> list[dict[str, float]]:
        if not levels:
            return []
        threshold = reference * threshold_pct / 100.0
        clusters = []
        current = [sorted(levels)[0]]
        for level in sorted(levels)[1:]:
            if abs(level - (sum(current) / len(current))) <= threshold:
                current.append(level)
            else:
                clusters.append({"price": sum(current) / len(current), "count": float(len(current))})
                current = [level]
        clusters.append({"price": sum(current) / len(current), "count": float(len(current))})
        return sorted(clusters, key=lambda item: item["count"], reverse=True)
