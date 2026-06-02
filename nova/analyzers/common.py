"""Shared helpers for canonical NOVA analyzers.

The helpers keep analyzer modules small while preserving the NOVA contract:
analyzers observe market phenomena, emit lineage, and never own trade decisions.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional

from nova.analysis.models import AnalysisResult, AnalysisStatus, EvidenceRef, StateContribution
from nova.analyzers.contracts import AnalysisPackage, AnalyzerContext, AnalyzerManifest
from nova.cards.models import CardDeck, CardInfluenceRights, EvidenceCard
from nova.core.evidence import CardStage, CardType, EvidenceTier
from nova.data.models import Candle, CandleSeries, MarketSnapshot
from nova.data.synthetic_tf import timeframe_to_minutes
from nova.matrix.models import ForecastContribution


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    if denominator == 0.0:
        return default
    return numerator / denominator


def ordered_candles(series: CandleSeries, lookback: int | None = None) -> List[Candle]:
    candles = sorted(series.candles, key=lambda item: item.open_time)
    return candles[-lookback:] if lookback is not None and lookback > 0 else candles


def latest_close(series: CandleSeries) -> Optional[float]:
    candle = series.latest_closed()
    return candle.close if candle else None


def evidence_refs_for_snapshot(
    snapshot: MarketSnapshot,
    *,
    series: CandleSeries | None = None,
    extra: Iterable[EvidenceRef] | None = None,
) -> List[EvidenceRef]:
    refs = [
        EvidenceRef(
            evidence_type="market_snapshot",
            source_id=snapshot.snapshot_id,
            description="NOVA MarketSnapshot used by analyzer.",
        )
    ]
    if series is not None:
        refs.append(
            EvidenceRef(
                evidence_type="candle_series",
                source_id=series.series_id,
                description=f"{series.symbol} {series.timeframe} candle series from MarketSnapshot.",
            )
        )
    refs.extend(list(extra or []))
    return refs


def no_data_package(manifest: AnalyzerManifest, context: AnalyzerContext, reason: str) -> AnalysisPackage:
    result = AnalysisResult(
        analyzer_name=manifest.name,
        analyzer_version=manifest.version,
        symbol=context.symbol,
        timeframe=context.timeframe,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        market_snapshot_id=context.market_snapshot_id,
        confidence=0.0,
        quality=0.0,
        status=AnalysisStatus.NO_DATA,
        payload={"reason": reason, "not_trade_decision": True},
        parameters_used=context.parameters,
        input_ids=context.available_data_ids,
        dependency_group=manifest.dependency_group,
        stage=CardStage.RAW,
        evidence_tier=EvidenceTier.PRIMARY,
        feedback_depth=0,
    )
    return AnalysisPackage(analysis_result=result, card_deck=CardDeck(cycle_id=context.cycle_id))


def build_package(
    *,
    manifest: AnalyzerManifest,
    context: AnalyzerContext,
    payload: dict[str, Any],
    confidence: float,
    quality: float,
    evidence_refs: List[EvidenceRef],
    forecast_specs: Iterable[dict[str, Any]] | None = None,
    state_type: str | None = None,
    state_value: Any | None = None,
    state_severity: str = "INFO",
    ttl_sec: int = 300,
) -> AnalysisPackage:
    payload = {
        "not_trade_decision": True,
        "probability_semantics": "analyzer_observation_probability_not_executor_permission",
        "confidence_semantics": "math_observation_reliability_not_trade_confidence",
        **payload,
    }
    bounded_confidence = clamp(confidence, 0.1, 0.9)
    result = AnalysisResult(
        analyzer_name=manifest.name,
        analyzer_version=manifest.version,
        symbol=context.symbol,
        timeframe=context.timeframe,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        market_snapshot_id=context.market_snapshot_id,
        confidence=bounded_confidence,
        quality=clamp(quality),
        status=AnalysisStatus.OK,
        payload=payload,
        parameters_used=context.parameters,
        input_ids=context.available_data_ids,
        dependency_group=manifest.dependency_group,
        stage=CardStage.RAW,
        evidence_tier=EvidenceTier.PRIMARY,
        feedback_depth=0,
        evidence_refs=evidence_refs,
    )

    cards: List[EvidenceCard] = []
    forecast_card: EvidenceCard | None = None
    specs = list(forecast_specs or [])
    if specs:
        forecast_card = EvidenceCard.primary_forecast(
            cycle_id=context.cycle_id,
            source_analysis_result_id=result.analysis_result_id,
            source_analyzer=manifest.name,
            payload=payload,
            evidence_refs=evidence_refs,
        )
        cards.append(forecast_card)

    state_card: EvidenceCard | None = None
    if state_type is not None:
        state_card = EvidenceCard(
            card_type=CardType.STATE,
            stage=CardStage.RAW,
            tier=EvidenceTier.PRIMARY,
            cycle_id=context.cycle_id,
            source_analysis_result_id=result.analysis_result_id,
            source_analyzer=manifest.name,
            rights=CardInfluenceRights(can_affect_decision_context=True),
            evidence_refs=evidence_refs,
            payload=payload,
        )
        cards.append(state_card)

    forecasts = [
        ForecastContribution(
            symbol=context.symbol,
            source_analysis_result_id=result.analysis_result_id,
            timeframe=context.timeframe,
            horizon_min=max(1, int(spec.get("horizon_min", timeframe_to_minutes(context.timeframe)))),
            price_low=float(spec["price_low"]),
            price_high=float(spec["price_high"]),
            probability=clamp(float(spec.get("probability", bounded_confidence)), 0.1, 0.9),
            confidence=clamp(float(spec.get("confidence", bounded_confidence)), 0.1, 0.9),
            direction=str(spec.get("direction", "CONTEXT")),
            weight=clamp(float(spec.get("weight", 1.0))),
            dependency_group=manifest.dependency_group,
            decay_sec=max(60, int(spec.get("decay_sec", ttl_sec))),
            stage=CardStage.RAW,
            evidence_tier=EvidenceTier.PRIMARY,
            feedback_depth=0,
            source_card_ids=[forecast_card.card_id] if forecast_card else [],
            phenomenon=str(spec.get("phenomenon", payload.get("phenomenon", manifest.name))),
            field_shape=str(spec.get("field_shape", "bounded_price_area")),
            invalidation_price=spec.get("invalidation_price"),
            evidence_refs=evidence_refs,
            payload={**payload, **dict(spec.get("payload", {}))},
        )
        for spec in specs
        if float(spec["price_low"]) > 0.0 and float(spec["price_high"]) >= float(spec["price_low"])
    ]

    states = []
    if state_type is not None:
        states.append(
            StateContribution(
                source_analysis_result_id=result.analysis_result_id,
                state_type=state_type,
                value=state_value if state_value is not None else payload,
                confidence=bounded_confidence,
                severity=state_severity,
                ttl_sec=ttl_sec,
                stage=CardStage.RAW,
                evidence_tier=EvidenceTier.PRIMARY,
                feedback_depth=0,
                source_card_ids=[state_card.card_id] if state_card else [],
                evidence_refs=evidence_refs,
            )
        )
    return AnalysisPackage(
        analysis_result=result,
        card_deck=CardDeck(cycle_id=context.cycle_id, cards=cards),
        forecast_contributions=forecasts,
        state_contributions=states,
    )

