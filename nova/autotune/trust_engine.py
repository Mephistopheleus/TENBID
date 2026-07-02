"""Trust accounting from traceable scenario outcomes.

The engine produces conservative profile-change proposals. It does not rewrite
Canon, safety limits, secrets or executor mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from nova.autotune.models import AutotuneRecommendation
from nova.shadow.outcome import OutcomeResult, ScenarioOutcome


@dataclass(frozen=True)
class TrustUpdateResult:
    recommendation: Optional[AutotuneRecommendation]
    sample_count: int
    win_count: int
    loss_count: int
    flat_count: int
    proposed_trust_points: float
    reason: str
    diagnostics: dict[str, Any] | None = None


class TrustEngine:
    def build_recommendation(
        self,
        *,
        target_profile_id: str,
        profile_values: dict[str, Any],
        outcomes: Iterable[ScenarioOutcome],
        evidence_ids: list[str] | None = None,
    ) -> TrustUpdateResult:
        samples = list(outcomes)
        sample_count = len(samples)
        current_rr = float(profile_values.get("target_rr_min", 1.2))
        current_edge = float(profile_values.get("min_net_edge_pct", 0.12))
        if sample_count <= 0:
            return TrustUpdateResult(None, 0, 0, 0, 0, 0.0, "no_traceable_outcomes", {})

        wins = sum(1 for outcome in samples if outcome.result == OutcomeResult.OBSERVED_WIN)
        losses = sum(1 for outcome in samples if outcome.result == OutcomeResult.OBSERVED_LOSS)
        flats = sum(1 for outcome in samples if outcome.result == OutcomeResult.OBSERVED_FLAT)
        winrate = wins / sample_count
        avg_net_pnl = sum(outcome.net_pnl_pct for outcome in samples) / sample_count
        maturity = 1.0
        diagnostics = self._diagnostics(samples)
        
        # Adjust decision thresholds based on performance, not analyzer trust
        rr_adjustment = self._threshold_adjustment(
            current=current_rr,
            winrate=winrate,
            avg_net_pnl=avg_net_pnl,
            low=0.8,
            high=3.0,
            step=0.05,
        )
        edge_adjustment = self._threshold_adjustment(
            current=current_edge,
            winrate=winrate,
            avg_net_pnl=avg_net_pnl,
            low=0.05,
            high=1.0,
            step=0.02,
        )
        parameter_changes: dict[str, object] = {
            "shadow_outcome_sample_count": sample_count,
        }
        target_specs = ["shadow_outcome_sample_count"]
        if rr_adjustment is not None:
            parameter_changes["target_rr_min"] = rr_adjustment
            target_specs.append("target_rr_min")
        if edge_adjustment is not None:
            parameter_changes["min_net_edge_pct"] = edge_adjustment
            target_specs.append("min_net_edge_pct")
        
        proposed_trust = float(profile_values.get("market_structure_analyzer_trust_points", 0.1))
        
        if not parameter_changes or len(parameter_changes) == 1 and "shadow_outcome_sample_count" in parameter_changes:
            return TrustUpdateResult(None, sample_count, wins, losses, flats, proposed_trust, "no_significant_changes", diagnostics)

        recommendation = AutotuneRecommendation(
            target_profile_id=target_profile_id,
            parameter_changes=parameter_changes,
            evidence_ids=evidence_ids or [],
            sample_size=sample_count,
            confidence=maturity,
            reason=(
                "traceable_outcome_threshold_update; "
                f"wins={wins}, losses={losses}, flats={flats}, avg_net_pnl={avg_net_pnl:.4f}, maturity={maturity:.4f}"
            ),
            target_parameter_specs=target_specs,
            rollback_condition="owner_revert_or_negative_traceable_outcome_drift",
        )
        return TrustUpdateResult(recommendation, sample_count, wins, losses, flats, proposed_trust, "recommendation_created", diagnostics)

    @staticmethod
    def _threshold_adjustment(
        *,
        current: float,
        winrate: float,
        avg_net_pnl: float,
        low: float,
        high: float,
        step: float,
    ) -> float | None:
        proposed = current
        if winrate < 0.45 or avg_net_pnl < 0.0:
            proposed = min(high, current + step)
        elif winrate > 0.58 and avg_net_pnl > 0.0:
            proposed = max(low, current - step)
        proposed = round(proposed, 4)
        return proposed if abs(proposed - current) >= 0.0001 else None

    @staticmethod
    def _diagnostics(samples: list[ScenarioOutcome]) -> dict[str, Any]:
        recheck = 0
        orderbook_missing = 0
        close_methods: dict[str, int] = {}
        for outcome in samples:
            payload = outcome.payload or {}
            if payload.get("recheck_required") is True:
                recheck += 1
            state = payload.get("state_liquidity_state") or payload.get("liquidity_state")
            if state and state != "orderbook_available":
                orderbook_missing += 1
            close_methods[outcome.resolution_method] = close_methods.get(outcome.resolution_method, 0) + 1
        count = max(1, len(samples))
        return {
            "recheck_rate": recheck / count,
            "orderbook_missing_rate": orderbook_missing / count,
            "resolution_methods": close_methods,
        }
