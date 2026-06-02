"""Canonical NOVA volume profile analyzer."""

from __future__ import annotations

from typing import Any

from nova.analyzers.common import build_package, clamp, evidence_refs_for_snapshot, no_data_package, ordered_candles, safe_div
from nova.analyzers.contracts import AnalysisPackage, AnalyzerContext, AnalyzerManifest
from nova.core.evidence import CardType
from nova.data.synthetic_tf import timeframe_to_minutes


class VolumeProfileAnalyzer:
    manifest = AnalyzerManifest(
        name="volume_profile_analyzer",
        version="0.1.0",
        description="Builds POC/value-area/liquidity-node observations from OHLCV candles.",
        dependency_group="volume_profile_ohlcv",
        required_inputs=["MarketSnapshot.candles.volume"],
        supported_timeframes=["5m"],
        output_card_types=[CardType.FORECAST, CardType.STATE],
        parameter_names=["volume_profile_lookback_candles", "volume_profile_buckets", "volume_profile_horizon_bars"],
    )

    def analyze(self, context: AnalyzerContext) -> AnalysisPackage:
        snapshot = context.market_snapshot
        if snapshot is None:
            return no_data_package(self.manifest, context, "missing_market_snapshot")
        series = snapshot.candle_series(context.timeframe, context.symbol)
        if series is None or series.count < 12:
            return no_data_package(self.manifest, context, "insufficient_candles")

        lookback = max(12, int(context.parameters.get("volume_profile_lookback_candles", 96)))
        bucket_count = max(8, min(120, int(context.parameters.get("volume_profile_buckets", 36))))
        horizon_bars = max(1, int(context.parameters.get("volume_profile_horizon_bars", 6)))
        candles = ordered_candles(series, lookback)
        low = min(item.low for item in candles)
        high = max(item.high for item in candles)
        if low <= 0.0 or high <= low:
            return no_data_package(self.manifest, context, "flat_or_invalid_price_range")

        bucket_width = (high - low) / bucket_count
        buckets = [0.0 for _ in range(bucket_count)]
        for candle in candles:
            typical = (candle.high + candle.low + candle.close) / 3.0
            index = min(bucket_count - 1, max(0, int((typical - low) / bucket_width)))
            buckets[index] += max(0.0, candle.volume)

        total_volume = sum(buckets)
        if total_volume <= 0.0:
            return no_data_package(self.manifest, context, "missing_volume")
        poc_index = max(range(bucket_count), key=lambda index: buckets[index])
        target_volume = total_volume * 0.70
        included = {poc_index}
        while sum(buckets[index] for index in included) < target_volume and len(included) < bucket_count:
            candidates = [index for index in (min(included) - 1, max(included) + 1) if 0 <= index < bucket_count]
            if not candidates:
                break
            included.add(max(candidates, key=lambda index: buckets[index]))

        poc_price = low + (poc_index + 0.5) * bucket_width
        val = low + min(included) * bucket_width
        vah = low + (max(included) + 1) * bucket_width
        nodes = self._nodes(buckets, low, bucket_width, total_volume)
        latest = candles[-1].close
        profile_width_pct = safe_div(vah - val, latest, 0.0) * 100.0
        concentration = max(buckets) / total_volume
        confidence = clamp(0.25 + concentration * 1.8 + min(profile_width_pct / 8.0, 0.25), 0.1, 0.9)

        payload: dict[str, Any] = {
            "phenomenon": "volume_acceptance_area",
            "lookback_candles": len(candles),
            "bucket_count": bucket_count,
            "poc_price": poc_price,
            "value_area_low": val,
            "value_area_high": vah,
            "profile_width_pct": profile_width_pct,
            "volume_concentration": concentration,
            "high_volume_nodes": nodes["high"],
            "low_volume_nodes": nodes["low"],
            "donor_legacy_idea": "POC/VAH/VAL/nodes_without_profile_direction_vote",
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
                    "price_low": val,
                    "price_high": vah,
                    "horizon_min": horizon_min,
                    "probability": confidence,
                    "confidence": confidence,
                    "direction": "VALUE_AREA_CONTEXT",
                    "phenomenon": "volume_acceptance_area",
                    "field_shape": "value_area_band",
                }
            ],
            state_type="volume_profile_context",
            state_value=payload,
            ttl_sec=max(60, horizon_min * 60),
        )

    @staticmethod
    def _nodes(buckets: list[float], low: float, width: float, total: float) -> dict[str, list[dict[str, float]]]:
        average = total / max(1, len(buckets))
        high_nodes = []
        low_nodes = []
        for index, volume in enumerate(buckets):
            item = {"price": low + (index + 0.5) * width, "share": safe_div(volume, total)}
            if volume >= average * 1.6:
                high_nodes.append(item)
            elif volume <= average * 0.45:
                low_nodes.append(item)
        return {"high": high_nodes[:8], "low": low_nodes[:8]}
