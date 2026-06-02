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
        current = float(
            profile_values.get(
                "market_structure_analyzer_trust_points",
                profile_values.get("analyzer_initial_trust_points", 0.1),
            )
        )
        minimum = float(profile_values.get("analyzer_initial_trust_points", 0.1))
        minimum_samples = int(profile_values.get("minimum_shadow_samples_before_execution", 50))
        if sample_count <= 0:
            return TrustUpdateResult(None, 0, 0, 0, 0, current, "no_traceable_outcomes")

        wins = sum(1 for outcome in samples if outcome.result == OutcomeResult.OBSERVED_WIN)
        losses = sum(1 for outcome in samples if outcome.result == OutcomeResult.OBSERVED_LOSS)
        flats = sum(1 for outcome in samples if outcome.result == OutcomeResult.OBSERVED_FLAT)
        winrate = wins / sample_count
        avg_net_pnl = sum(outcome.net_pnl_pct for outcome in samples) / sample_count
        maturity = min(1.0, sample_count / max(1, minimum_samples))
        directional_score = (winrate - 0.5) * 0.20
        pnl_score = max(-0.05, min(0.05, avg_net_pnl / 100.0))
        proposed = max(minimum, min(0.9, current + (directional_score + pnl_score) * maturity))

        if abs(proposed - current) < 0.005:
            return TrustUpdateResult(None, sample_count, wins, losses, flats, proposed, "trust_delta_too_small")

        recommendation = AutotuneRecommendation(
            target_profile_id=target_profile_id,
            parameter_changes={
                "market_structure_analyzer_trust_points": round(proposed, 4),
                "shadow_outcome_sample_count": sample_count,
            },
            evidence_ids=evidence_ids or [],
            sample_size=sample_count,
            confidence=maturity,
            reason=(
                "traceable_outcome_trust_update; "
                f"wins={wins}, losses={losses}, flats={flats}, avg_net_pnl={avg_net_pnl:.4f}, maturity={maturity:.4f}"
            ),
            target_parameter_specs=[
                "market_structure_analyzer_trust_points",
                "shadow_outcome_sample_count",
            ],
            rollback_condition="owner_revert_or_negative_traceable_outcome_drift",
        )
        return TrustUpdateResult(recommendation, sample_count, wins, losses, flats, proposed, "recommendation_created")
