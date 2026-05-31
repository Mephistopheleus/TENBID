"""First MarketSnapshot-backed structure analyzer.

The analyzer describes the current local price range as evidence/context. It does
not produce buy/sell/stop instructions and does not own trade decisions.
"""

from __future__ import annotations

from typing import Any, Dict, List

from nova.analysis.models import AnalysisResult, AnalysisStatus, EvidenceRef, StateContribution
from nova.analyzers.contracts import AnalysisPackage, AnalyzerContext, AnalyzerManifest
from nova.cards.models import CardDeck, CardInfluenceRights, EvidenceCard
from nova.core.evidence import CardStage, CardType, EvidenceTier
from nova.data.models import Candle
from nova.data.synthetic_tf import timeframe_to_minutes
from nova.matrix.models import ForecastContribution


class MarketStructureAnalyzer:
    manifest = AnalyzerManifest(
        name="market_structure_analyzer",
        version="0.1.0",
        description="Reads MarketSnapshot candles and emits bounded structure context evidence.",
        dependency_group="market_snapshot_ohlcv",
        required_inputs=["MarketSnapshot.candles"],
        supported_timeframes=["5m"],
        output_card_types=[CardType.FORECAST, CardType.STATE],
        parameter_names=["structure_lookback_candles", "structure_horizon_bars"],
        supports_raw=True,
        supports_validation=False,
        supports_recheck=False,
    )

    def analyze(self, context: AnalyzerContext) -> AnalysisPackage:
        if context.market_snapshot is None:
            return self._no_data_package(context, "missing_market_snapshot")

        series = context.market_snapshot.candle_series(context.timeframe, context.symbol)
        if series is None or series.count < 2:
            return self._no_data_package(context, "insufficient_candles")

        lookback = max(2, int(context.parameters.get("structure_lookback_candles", 48)))
        horizon_bars = max(1, int(context.parameters.get("structure_horizon_bars", 3)))
        candles = series.candles[-lookback:]
        metrics = self._metrics(candles)
        timeframe_minutes = timeframe_to_minutes(context.timeframe)
        horizon_min = timeframe_minutes * horizon_bars
        quality = min(context.market_snapshot.quality.score, series.quality.score)
        confidence = max(0.0, min(1.0, quality * min(1.0, len(candles) / lookback)))

        evidence_refs = [
            EvidenceRef(
                evidence_type="market_snapshot",
                source_id=context.market_snapshot.snapshot_id,
                description="Refreshed NOVA MarketSnapshot used by analyzer.",
            ),
            EvidenceRef(
                evidence_type="candle_series",
                source_id=series.series_id,
                description=f"{context.symbol} {context.timeframe} candle series from MarketSnapshot.",
            ),
        ]
        payload: Dict[str, Any] = {
            "phenomenon": "recent_range_context",
            "not_trade_decision": True,
            "decision_owner": "DecisionEngine/TradeCalculator/RiskManager/SafetyKernel",
            "lookback_candles": len(candles),
            "requested_lookback_candles": lookback,
            "horizon_min": horizon_min,
            "metrics": metrics,
            "probability_semantics": "evidence_presence_not_trade_direction",
        }
        result = AnalysisResult(
            analyzer_name=self.manifest.name,
            analyzer_version=self.manifest.version,
            symbol=context.symbol,
            timeframe=context.timeframe,
            run_id=context.run_id,
            cycle_id=context.cycle_id,
            market_snapshot_id=context.market_snapshot_id,
            confidence=confidence,
            quality=quality,
            status=AnalysisStatus.OK,
            payload=payload,
            parameters_used=context.parameters,
            input_ids=context.available_data_ids,
            dependency_group=self.manifest.dependency_group,
            stage=CardStage.RAW,
            evidence_tier=EvidenceTier.PRIMARY,
            feedback_depth=0,
            evidence_refs=evidence_refs,
        )
        forecast_card = EvidenceCard.primary_forecast(
            cycle_id=context.cycle_id,
            source_analysis_result_id=result.analysis_result_id,
            source_analyzer=self.manifest.name,
            payload=payload,
            evidence_refs=evidence_refs,
        )
        state_card = EvidenceCard(
            card_type=CardType.STATE,
            stage=CardStage.RAW,
            tier=EvidenceTier.PRIMARY,
            cycle_id=context.cycle_id,
            source_analysis_result_id=result.analysis_result_id,
            source_analyzer=self.manifest.name,
            rights=CardInfluenceRights(can_affect_decision_context=True),
            evidence_refs=evidence_refs,
            payload=payload,
        )
        contribution = ForecastContribution(
            symbol=context.symbol,
            source_analysis_result_id=result.analysis_result_id,
            timeframe=context.timeframe,
            horizon_min=horizon_min,
            price_low=metrics["range_low"],
            price_high=metrics["range_high"],
            probability=confidence,
            confidence=confidence,
            direction="CONTEXT",
            dependency_group=self.manifest.dependency_group,
            decay_sec=max(60, horizon_min * 60),
            stage=CardStage.RAW,
            evidence_tier=EvidenceTier.PRIMARY,
            feedback_depth=0,
            source_card_ids=[forecast_card.card_id],
            phenomenon="recent_range_context",
            field_shape="bounded_price_range",
            evidence_refs=evidence_refs,
            payload=payload,
        )
        state_contribution = StateContribution(
            source_analysis_result_id=result.analysis_result_id,
            state_type="market_structure_context",
            value=metrics,
            confidence=confidence,
            severity="INFO",
            ttl_sec=max(60, horizon_min * 60),
            stage=CardStage.RAW,
            evidence_tier=EvidenceTier.PRIMARY,
            feedback_depth=0,
            source_card_ids=[state_card.card_id],
            evidence_refs=evidence_refs,
        )
        return AnalysisPackage(
            analysis_result=result,
            card_deck=CardDeck(cycle_id=context.cycle_id, cards=[forecast_card, state_card]),
            forecast_contributions=[contribution],
            state_contributions=[state_contribution],
        )

    def _no_data_package(self, context: AnalyzerContext, reason: str) -> AnalysisPackage:
        result = AnalysisResult(
            analyzer_name=self.manifest.name,
            analyzer_version=self.manifest.version,
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
            dependency_group=self.manifest.dependency_group,
            stage=CardStage.RAW,
            evidence_tier=EvidenceTier.PRIMARY,
            feedback_depth=0,
        )
        return AnalysisPackage(analysis_result=result, card_deck=CardDeck(cycle_id=context.cycle_id))

    @staticmethod
    def _metrics(candles: List[Candle]) -> Dict[str, float]:
        ordered = sorted(candles, key=lambda candle: candle.open_time)
        latest = ordered[-1]
        range_low = min(candle.low for candle in ordered)
        range_high = max(candle.high for candle in ordered)
        range_span = max(0.0, range_high - range_low)
        range_position = 0.5 if range_span == 0.0 else (latest.close - range_low) / range_span
        base_price = latest.close if latest.close else 1.0
        first_open = ordered[0].open if ordered[0].open else 1.0
        return {
            "range_low": range_low,
            "range_high": range_high,
            "latest_close": latest.close,
            "range_width_pct": (range_span / base_price) * 100.0,
            "range_position": max(0.0, min(1.0, range_position)),
            "recent_return_pct": ((latest.close - first_open) / first_open) * 100.0,
        }
