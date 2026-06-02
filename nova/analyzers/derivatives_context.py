"""Canonical NOVA derivatives context analyzer."""

from __future__ import annotations

from nova.analysis.models import EvidenceRef
from nova.analyzers.common import build_package, clamp, evidence_refs_for_snapshot, no_data_package
from nova.analyzers.contracts import AnalysisPackage, AnalyzerContext, AnalyzerManifest
from nova.core.evidence import CardType
from nova.data.synthetic_tf import timeframe_to_minutes


class DerivativesContextAnalyzer:
    manifest = AnalyzerManifest(
        name="derivatives_context_analyzer",
        version="0.1.0",
        description="Observes funding, open interest and long/short crowding when derivatives data exists.",
        dependency_group="derivatives_context",
        required_inputs=["MarketSnapshot.derivatives"],
        supported_timeframes=["5m"],
        output_card_types=[CardType.STATE],
        parameter_names=["derivatives_funding_extreme_abs", "derivatives_horizon_bars"],
    )

    def analyze(self, context: AnalyzerContext) -> AnalysisPackage:
        snapshot = context.market_snapshot
        if snapshot is None:
            return no_data_package(self.manifest, context, "missing_market_snapshot")
        derivatives = snapshot.derivatives
        if derivatives is None:
            return no_data_package(self.manifest, context, "derivatives_not_loaded")
        has_any = derivatives.funding_rate is not None or derivatives.open_interest is not None or derivatives.long_short_ratio is not None
        if not has_any:
            return no_data_package(self.manifest, context, "empty_derivatives_snapshot")
        funding = derivatives.funding_rate.funding_rate if derivatives.funding_rate else None
        oi = derivatives.open_interest.open_interest if derivatives.open_interest else None
        ratio = derivatives.long_short_ratio.long_short_ratio if derivatives.long_short_ratio else None
        extreme = max(0.0001, float(context.parameters.get("derivatives_funding_extreme_abs", 0.0008)))
        funding_pressure = None if funding is None else clamp(abs(funding) / extreme)
        crowding = None if ratio is None else clamp(abs(ratio - 1.0) / 1.0)
        squeeze_risk = clamp((funding_pressure or 0.0) * 0.45 + (crowding or 0.0) * 0.45 + (0.10 if oi is not None and oi > 0 else 0.0))
        confidence = clamp(0.2 + (0.25 if funding is not None else 0.0) + (0.20 if oi is not None else 0.0) + (0.20 if ratio is not None else 0.0) + squeeze_risk * 0.20, 0.1, 0.9)
        payload = {
            "phenomenon": "derivatives_crowding_context",
            "funding_rate": funding,
            "open_interest": oi,
            "long_short_ratio": ratio,
            "funding_pressure": funding_pressure,
            "crowding_pressure": crowding,
            "squeeze_risk_observation": squeeze_risk,
            "dominant_risk": self._dominant_risk(funding, ratio),
            "donor_legacy_idea": "funding/OI/ratio/liquidation_context_without_sentiment_score_permission",
        }
        horizon_min = max(1, int(context.parameters.get("derivatives_horizon_bars", 6))) * timeframe_to_minutes(context.timeframe)
        return build_package(
            manifest=self.manifest,
            context=context,
            payload=payload,
            confidence=confidence,
            quality=min(snapshot.quality.score, derivatives.quality.score),
            evidence_refs=evidence_refs_for_snapshot(
                snapshot,
                extra=[EvidenceRef("derivatives_snapshot", derivatives.snapshot_id, "Derivatives context snapshot.")],
            ),
            forecast_specs=[],
            state_type="derivatives_context",
            state_value=payload,
            state_severity="WARN" if squeeze_risk >= 0.65 else "INFO",
            ttl_sec=max(60, horizon_min * 60),
        )

    @staticmethod
    def _dominant_risk(funding: float | None, ratio: float | None) -> str:
        if funding is None and ratio is None:
            return "UNKNOWN"
        if funding is not None and funding > 0.0 and ratio is not None and ratio > 1.3:
            return "LONG_CROWDING"
        if funding is not None and funding < 0.0 and ratio is not None and ratio < 0.75:
            return "SHORT_CROWDING"
        if funding is not None and abs(funding) > 0.0008:
            return "FUNDING_PRESSURE"
        return "DERIVATIVES_CONTEXT_PRESENT"
