"""Contract-test analyzers.

These analyzers are not trading logic. They are deterministic fixtures for
testing the analyzer/card/matrix persistence pipeline before real analyzers are
introduced.
"""

from __future__ import annotations

from nova.analysis.models import AnalysisResult, EvidenceRef
from nova.analyzers.contracts import AnalysisPackage, AnalyzerContext, AnalyzerManifest
from nova.cards.models import CardDeck, EvidenceCard
from nova.core.evidence import CardStage, CardType, EvidenceTier
from nova.matrix.models import ForecastContribution


class StaticTestAnalyzer:
    manifest = AnalyzerManifest(
        name="static_test_analyzer",
        version="0.1.0",
        description="Deterministic fixture analyzer for pipeline tests.",
        dependency_group="fixture",
        required_inputs=[],
        supported_timeframes=["5m"],
        output_card_types=[CardType.FORECAST, CardType.VALIDATION],
        parameter_names=["fixture_probability", "fixture_confidence"],
        supports_raw=True,
        supports_validation=True,
    )

    def analyze(self, context: AnalyzerContext) -> AnalysisPackage:
        if context.stage == CardStage.VALIDATION:
            return self._validation_package(context)
        return self._raw_package(context)

    def _raw_package(self, context: AnalyzerContext) -> AnalysisPackage:
        probability = float(context.parameters.get("fixture_probability", 0.60))
        confidence = float(context.parameters.get("fixture_confidence", 0.50))
        evidence = [EvidenceRef(evidence_type="fixture", source_id="static_test", description="Synthetic test evidence")]
        result = AnalysisResult(
            analyzer_name=self.manifest.name,
            analyzer_version=self.manifest.version,
            symbol=context.symbol,
            timeframe=context.timeframe,
            run_id=context.run_id,
            cycle_id=context.cycle_id,
            market_snapshot_id=context.market_snapshot_id,
            confidence=confidence,
            quality=1.0,
            status="OK",
            payload={"fixture": True, "stage": context.stage},
            parameters_used=context.parameters,
            input_ids=context.available_data_ids,
            dependency_group=self.manifest.dependency_group,
            stage=CardStage.RAW,
            evidence_tier=EvidenceTier.PRIMARY,
            feedback_depth=0,
            evidence_refs=evidence,
        )
        card = EvidenceCard.primary_forecast(
            cycle_id=context.cycle_id,
            source_analysis_result_id=result.analysis_result_id,
            source_analyzer=self.manifest.name,
            payload={
                "symbol": context.symbol,
                "timeframe": context.timeframe,
                "horizon_min": 15,
                "price_low": 0.0,
                "price_high": 0.0,
                "probability": probability,
                "confidence": confidence,
                "phenomenon": "fixture_field_seed",
            },
            evidence_refs=evidence,
        )
        contribution = ForecastContribution(
            symbol=context.symbol,
            source_analysis_result_id=result.analysis_result_id,
            timeframe=context.timeframe,
            horizon_min=15,
            price_low=0.0,
            price_high=0.0,
            probability=probability,
            confidence=confidence,
            direction="NEUTRAL",
            dependency_group=self.manifest.dependency_group,
            source_card_ids=[card.card_id],
            phenomenon="fixture_field_seed",
            field_shape="core_halo",
            evidence_refs=evidence,
            payload={"fixture": True},
        )
        return AnalysisPackage(
            analysis_result=result,
            card_deck=CardDeck(cycle_id=context.cycle_id, cards=[card]),
            forecast_contributions=[contribution],
        )

    def _validation_package(self, context: AnalyzerContext) -> AnalysisPackage:
        if context.input_matrix_id is None:
            raise ValueError("Validation pass requires input_matrix_id")
        result = AnalysisResult(
            analyzer_name=self.manifest.name,
            analyzer_version=self.manifest.version,
            symbol=context.symbol,
            timeframe=context.timeframe,
            run_id=context.run_id,
            cycle_id=context.cycle_id,
            market_snapshot_id=context.market_snapshot_id,
            confidence=0.0,
            quality=1.0,
            status="OK",
            payload={"fixture": True, "stage": context.stage, "input_matrix_id": context.input_matrix_id},
            parameters_used=context.parameters,
            input_ids=context.available_data_ids,
            dependency_group=self.manifest.dependency_group,
            stage=CardStage.VALIDATION,
            evidence_tier=EvidenceTier.META,
            input_matrix_id=context.input_matrix_id,
            parent_card_ids=context.parent_card_ids,
            feedback_depth=context.feedback_depth,
        )
        card = EvidenceCard.validation(
            cycle_id=context.cycle_id,
            source_analysis_result_id=result.analysis_result_id,
            source_analyzer=self.manifest.name,
            target_zone_ids=[],
            payload={"fixture": True, "validation": "no_zone_target_yet"},
            input_matrix_id=context.input_matrix_id,
            parent_card_ids=context.parent_card_ids,
        )
        return AnalysisPackage(
            analysis_result=result,
            card_deck=CardDeck(cycle_id=context.cycle_id, cards=[card]),
        )

