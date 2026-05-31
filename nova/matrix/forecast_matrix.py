"""Forecast matrix engine.

Builds a sparse primary matrix from raw primary ForecastContributions. This is
not a decision engine and it does not densify empty price-time regions.
"""

from __future__ import annotations

from typing import Iterable, List

from nova.core.evidence import MatrixFieldRole, MatrixLayer
from nova.matrix.models import ForecastContribution, ForecastMatrix, MatrixZone
from nova.matrix.validators import MatrixValidator


class ForecastMatrixEngine:
    def build(self, cycle_id: str, symbol: str, contributions: Iterable[ForecastContribution]) -> ForecastMatrix:
        contributions = list(contributions)
        MatrixValidator().validate_primary_contributions(contributions)
        zones = [self._zone_from_contribution(contribution) for contribution in contributions]
        source_card_ids: List[str] = []
        for contribution in contributions:
            source_card_ids.extend(contribution.source_card_ids)
        return ForecastMatrix(
            symbol=symbol.upper(),
            cycle_id=cycle_id,
            zones=zones,
            contributor_ids=[contribution.contribution_id for contribution in contributions],
            source_card_ids=source_card_ids,
            primary_only=True,
            matrix_layer=MatrixLayer.PRIMARY,
        )

    @staticmethod
    def _zone_from_contribution(contribution: ForecastContribution) -> MatrixZone:
        confidence = max(0.0, min(1.0, contribution.confidence * contribution.weight))
        probability = max(0.0, min(1.0, contribution.probability))
        return MatrixZone(
            price_low=contribution.price_low,
            price_high=contribution.price_high,
            horizon_min=contribution.horizon_min,
            scenario=contribution.direction,
            probability=probability,
            confidence=confidence,
            contributor_ids=[contribution.contribution_id],
            field_role=MatrixFieldRole.CORE,
            core_price_low=contribution.price_low,
            core_price_high=contribution.price_high,
            agreement_score=confidence,
            conflict_score=0.0,
            importance_score=probability * confidence,
            source_analysis_result_ids=[contribution.source_analysis_result_id],
            source_card_ids=contribution.source_card_ids,
            payload={
                "phenomenon": contribution.phenomenon,
                "field_shape": contribution.field_shape,
                "dependency_group": contribution.dependency_group,
                "source_contribution_id": contribution.contribution_id,
                "sparse_field_seed": True,
                "not_trade_decision": True,
            },
        )
