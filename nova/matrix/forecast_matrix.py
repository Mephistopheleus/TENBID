"""Forecast matrix engine.

Builds a sparse primary matrix from raw primary ForecastContributions. Compatible
overlapping contributions can be grouped into one evidence-backed island;
incompatible overlaps become tension metadata. This is not a decision engine and
it does not densify empty price-time regions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Sequence

from nova.core.evidence import MatrixFieldRole, MatrixLayer, MatrixZoneStatus
from nova.matrix.models import ForecastContribution, ForecastMatrix, MatrixZone
from nova.matrix.validators import MatrixValidator


@dataclass
class _ContributionGroup:
    contributions: List[ForecastContribution] = field(default_factory=list)

    def add(self, contribution: ForecastContribution) -> None:
        self.contributions.append(contribution)


class ForecastMatrixEngine:
    def build(self, cycle_id: str, symbol: str, contributions: Iterable[ForecastContribution]) -> ForecastMatrix:
        contributions = list(contributions)
        MatrixValidator().validate_primary_contributions(contributions)
        groups = self._group_compatible_contributions(contributions)
        core_zones = [self._zone_from_group(group) for group in groups]
        zones = [*core_zones, *self._tension_zones(core_zones)]
        source_card_ids: List[str] = []
        for contribution in contributions:
            source_card_ids.extend(contribution.source_card_ids)
        return ForecastMatrix(
            symbol=symbol.upper(),
            cycle_id=cycle_id,
            zones=zones,
            contributor_ids=[contribution.contribution_id for contribution in contributions],
            source_card_ids=_unique(source_card_ids),
            primary_only=True,
            matrix_layer=MatrixLayer.PRIMARY,
        )

    def _group_compatible_contributions(
        self,
        contributions: Sequence[ForecastContribution],
    ) -> List[_ContributionGroup]:
        groups: List[_ContributionGroup] = []
        for contribution in sorted(contributions, key=lambda item: (item.horizon_min, item.price_low, item.price_high)):
            for group in groups:
                if self._compatible_with_group(contribution, group):
                    group.add(contribution)
                    break
            else:
                groups.append(_ContributionGroup([contribution]))
        return groups

    def _compatible_with_group(self, contribution: ForecastContribution, group: _ContributionGroup) -> bool:
        return all(self._compatible(contribution, existing) for existing in group.contributions)

    @staticmethod
    def _compatible(left: ForecastContribution, right: ForecastContribution) -> bool:
        if left.direction != right.direction:
            return False
        if left.phenomenon != right.phenomenon:
            return False
        if left.field_shape != right.field_shape:
            return False
        horizon_max = max(left.horizon_min, right.horizon_min, 1)
        horizon_min = max(min(left.horizon_min, right.horizon_min), 1)
        if horizon_max / horizon_min > 1.5:
            return False
        return _ranges_overlap(left.price_low, left.price_high, right.price_low, right.price_high)

    def _zone_from_group(self, group: _ContributionGroup) -> MatrixZone:
        contributions = group.contributions
        weighted_probability = _weighted_average(
            [(item.probability, self._effective_weight(item)) for item in contributions]
        )
        weighted_confidence = _weighted_average(
            [(item.confidence, self._effective_weight(item)) for item in contributions]
        )
        dependency_groups = sorted({item.dependency_group for item in contributions})
        confidence = max(0.0, min(1.0, weighted_confidence))
        core_price_low = max(item.price_low for item in contributions)
        core_price_high = min(item.price_high for item in contributions)
        halo_price_low = min(item.price_low for item in contributions)
        halo_price_high = max(item.price_high for item in contributions)
        horizon_min = round(_weighted_average([(item.horizon_min, self._effective_weight(item)) for item in contributions]))
        agreement_score = confidence
        contributor_ids = [item.contribution_id for item in contributions]
        source_analysis_result_ids = _unique(item.source_analysis_result_id for item in contributions)
        source_card_ids = _unique(card_id for item in contributions for card_id in item.source_card_ids)
        first = contributions[0]
        return MatrixZone(
            price_low=core_price_low,
            price_high=core_price_high,
            horizon_min=horizon_min,
            scenario=first.direction,
            probability=max(0.0, min(1.0, weighted_probability)),
            confidence=confidence,
            contributor_ids=contributor_ids,
            field_role=MatrixFieldRole.CORE,
            core_price_low=core_price_low,
            core_price_high=core_price_high,
            halo_price_low=halo_price_low,
            halo_price_high=halo_price_high,
            agreement_score=agreement_score,
            conflict_score=0.0,
            importance_score=max(0.0, min(1.0, weighted_probability)) * confidence,
            source_analysis_result_ids=source_analysis_result_ids,
            source_card_ids=source_card_ids,
            payload={
                "phenomenon": first.phenomenon,
                "field_shape": first.field_shape,
                "dependency_groups": dependency_groups,
                "source_contribution_ids": contributor_ids,
                "grouped_contribution_count": len(contributions),
                "grouping_rule": "compatible_overlap_same_scenario_phenomenon_shape_horizon",
                "halo_from_union": True,
                "sparse_field_seed": True,
                "not_trade_decision": True,
            },
        )

    def _tension_zones(self, zones: Sequence[MatrixZone]) -> List[MatrixZone]:
        tensions: List[MatrixZone] = []
        for index, left in enumerate(zones):
            for right in zones[index + 1 :]:
                if not self._zones_in_tension(left, right):
                    continue
                overlap_low = max(left.price_low, right.price_low)
                overlap_high = min(left.price_high, right.price_high)
                if overlap_low > overlap_high:
                    continue
                conflict_score = min(left.confidence, right.confidence) * _overlap_ratio(
                    left.price_low,
                    left.price_high,
                    right.price_low,
                    right.price_high,
                )
                tensions.append(
                    MatrixZone(
                        price_low=overlap_low,
                        price_high=overlap_high,
                        horizon_min=max(left.horizon_min, right.horizon_min),
                        scenario="TENSION",
                        probability=0.0,
                        confidence=min(left.confidence, right.confidence),
                        contributor_ids=_unique([*left.contributor_ids, *right.contributor_ids]),
                        field_role=MatrixFieldRole.TENSION,
                        status=MatrixZoneStatus.NEEDS_RECHECK,
                        core_price_low=overlap_low,
                        core_price_high=overlap_high,
                        agreement_score=0.0,
                        conflict_score=conflict_score,
                        importance_score=conflict_score,
                        source_analysis_result_ids=_unique(
                            [*left.source_analysis_result_ids, *right.source_analysis_result_ids]
                        ),
                        source_card_ids=_unique([*left.source_card_ids, *right.source_card_ids]),
                        recheck_reasons=["overlapping_incompatible_primary_fields"],
                        payload={
                            "source_zone_ids": [left.zone_id, right.zone_id],
                            "left_scenario": left.scenario,
                            "right_scenario": right.scenario,
                            "left_phenomenon": left.payload.get("phenomenon"),
                            "right_phenomenon": right.payload.get("phenomenon"),
                            "tension_type": "overlapping_incompatible_primary_fields",
                            "not_trade_decision": True,
                        },
                    )
                )
        return tensions

    @staticmethod
    def _zones_in_tension(left: MatrixZone, right: MatrixZone) -> bool:
        if not _ranges_overlap(left.price_low, left.price_high, right.price_low, right.price_high):
            return False
        horizon_max = max(left.horizon_min, right.horizon_min, 1)
        horizon_min = max(min(left.horizon_min, right.horizon_min), 1)
        if horizon_max / horizon_min > 1.5:
            return False
        same_scenario = left.scenario == right.scenario
        same_phenomenon = left.payload.get("phenomenon") == right.payload.get("phenomenon")
        same_shape = left.payload.get("field_shape") == right.payload.get("field_shape")
        return not (same_scenario and same_phenomenon and same_shape)

    @staticmethod
    def _effective_weight(contribution: ForecastContribution) -> float:
        return max(0.0, min(1.0, contribution.weight)) * max(0.0, min(1.0, contribution.confidence))


def _ranges_overlap(left_low: float, left_high: float, right_low: float, right_high: float) -> bool:
    return max(left_low, right_low) <= min(left_high, right_high)


def _overlap_ratio(left_low: float, left_high: float, right_low: float, right_high: float) -> float:
    overlap = max(0.0, min(left_high, right_high) - max(left_low, right_low))
    width = max(left_high, right_high) - min(left_low, right_low)
    if width <= 0.0:
        return 1.0 if _ranges_overlap(left_low, left_high, right_low, right_high) else 0.0
    return max(0.0, min(1.0, overlap / width))


def _weighted_average(items: Sequence[tuple[float, float]]) -> float:
    total_weight = sum(weight for _, weight in items)
    if total_weight <= 0.0:
        return sum(value for value, _ in items) / max(1, len(items))
    return sum(value * weight for value, weight in items) / total_weight


def _unique(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
