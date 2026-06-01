"""Build bounded scenario candidates from Matrix and State context."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from nova.core.evidence import MatrixFieldRole, MatrixZoneStatus
from nova.data.models import MarketSnapshot
from nova.matrix.models import ForecastMatrix, MatrixZone, StateMatrix
from nova.scenario.models import ScenarioBuildResult, ScenarioCandidate, ScenarioStatus


class ScenarioBuilder:
    """Converts the current market picture into a computable hypothesis.

    This layer deliberately avoids exchange/action language. It selects a
    calculation candidate only from evidence-backed Matrix zones and StateMatrix
    context. Executor-facing direction is produced later by TradeCalculator.
    """

    def build(
        self,
        *,
        cycle_id: str,
        forecast_matrix: ForecastMatrix | None,
        state_matrix: StateMatrix | None,
        market_snapshot: MarketSnapshot | None,
        profile_values: Dict[str, Any] | None = None,
    ) -> ScenarioBuildResult:
        profile_values = profile_values or {}
        if market_snapshot is None:
            return self._no_scenario("missing_market_snapshot")
        if forecast_matrix is None:
            return self._no_scenario("missing_forecast_matrix")
        if state_matrix is None:
            return self._no_scenario("missing_state_matrix")

        reference_price = self._latest_close(market_snapshot)
        if reference_price is None or reference_price <= 0.0:
            return self._no_scenario(
                "missing_reference_price",
                {
                    "market_snapshot_id": market_snapshot.snapshot_id,
                    "forecast_matrix_id": forecast_matrix.matrix_id,
                    "state_matrix_id": state_matrix.matrix_id,
                },
            )

        candidate_zones = list(self._candidate_zones(forecast_matrix.zones))
        if not candidate_zones:
            return self._no_scenario(
                "no_computable_matrix_zone",
                {
                    "forecast_matrix_id": forecast_matrix.matrix_id,
                    "state_matrix_id": state_matrix.matrix_id,
                    "zone_count": len(forecast_matrix.zones),
                },
            )

        zone = self._best_zone(candidate_zones, reference_price)
        recheck_required = zone.status == MatrixZoneStatus.NEEDS_RECHECK or bool(zone.recheck_reasons)
        if state_matrix.payload.get("recheck_reasons"):
            recheck_required = True

        analyzer_trust_points = self._analyzer_trust_points(profile_values)
        candidate = ScenarioCandidate(
            symbol=forecast_matrix.symbol,
            cycle_id=cycle_id,
            scenario_type=zone.scenario,
            price_low=zone.price_low,
            price_high=zone.price_high,
            reference_price=reference_price,
            horizon_min=zone.horizon_min,
            probability=zone.probability,
            confidence=zone.confidence,
            trust_score=analyzer_trust_points,
            forecast_matrix_id=forecast_matrix.matrix_id,
            state_matrix_id=state_matrix.matrix_id,
            source_zone_ids=[zone.zone_id],
            invalidation_price=self._invalidation_price(zone),
            recheck_required=recheck_required,
            reason="matrix_zone_has_computable_price_area",
            payload={
                "not_trade_decision": True,
                "market_snapshot_id": market_snapshot.snapshot_id,
                "selected_zone_id": zone.zone_id,
                "selected_zone_role": zone.field_role,
                "selected_zone_status": zone.status,
                "selected_zone_importance": zone.importance_score,
                "selected_zone_conflict_score": zone.conflict_score,
                "source_contributor_ids": zone.contributor_ids,
                "source_analysis_result_ids": zone.source_analysis_result_ids,
                "source_card_ids": zone.source_card_ids,
                "state_payload": state_matrix.payload,
                "autotuner_trust_points": analyzer_trust_points,
                "trust_points_semantics": "autotuner_points_start_minimum_until_shadow_outcomes_raise_them",
                "profile_thresholds": {
                    "confidence_threshold": profile_values.get("confidence_threshold"),
                    "matrix_dominance_threshold": profile_values.get("matrix_dominance_threshold"),
                    "min_net_edge_pct": profile_values.get("min_net_edge_pct"),
                },
            },
        )
        status = ScenarioStatus.RECHECK_REQUIRED if candidate.recheck_required else ScenarioStatus.CANDIDATE
        return ScenarioBuildResult(
            status=status,
            reason=candidate.reason,
            candidate=candidate,
            payload={
                "candidate_scenario_id": candidate.scenario_id,
                "forecast_matrix_id": forecast_matrix.matrix_id,
                "state_matrix_id": state_matrix.matrix_id,
                "candidate_zone_count": len(candidate_zones),
                "not_trade_decision": True,
            },
        )

    @staticmethod
    def _candidate_zones(zones: Iterable[MatrixZone]) -> Iterable[MatrixZone]:
        for zone in zones:
            if zone.field_role == MatrixFieldRole.TENSION:
                continue
            if zone.price_low <= 0.0 or zone.price_high <= 0.0:
                continue
            if zone.price_low > zone.price_high:
                continue
            yield zone

    @staticmethod
    def _best_zone(zones: list[MatrixZone], reference_price: float) -> MatrixZone:
        def score(zone: MatrixZone) -> float:
            center = (zone.price_low + zone.price_high) / 2.0
            distance_pct = abs(center - reference_price) / reference_price
            proximity = max(0.0, 1.0 - min(distance_pct / 0.05, 1.0))
            return (zone.probability * 0.35) + (zone.confidence * 0.30) + (zone.importance_score * 0.25) + (proximity * 0.10)

        return sorted(zones, key=score, reverse=True)[0]

    @staticmethod
    def _latest_close(snapshot: MarketSnapshot) -> Optional[float]:
        series = snapshot.candle_series(snapshot.base_timeframe, snapshot.primary_symbol)
        candle = series.latest_closed() if series else None
        return candle.close if candle else None

    @staticmethod
    def _invalidation_price(zone: MatrixZone) -> Optional[float]:
        payload_value = zone.payload.get("invalidation_price")
        if isinstance(payload_value, (int, float)):
            return float(payload_value)
        return None

    @staticmethod
    def _analyzer_trust_points(profile_values: Dict[str, Any]) -> float:
        raw = profile_values.get(
            "market_structure_analyzer_trust_points",
            profile_values.get("analyzer_initial_trust_points", 0.1),
        )
        return max(0.1, min(0.9, float(raw)))

    @staticmethod
    def _no_scenario(reason: str, payload: Dict[str, object] | None = None) -> ScenarioBuildResult:
        return ScenarioBuildResult(
            status=ScenarioStatus.NO_SCENARIO,
            reason=reason,
            payload={"not_trade_decision": True, **(payload or {})},
        )
