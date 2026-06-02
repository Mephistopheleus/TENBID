"""Build AutotuneRecommendation objects from traceable evidence.

This is a compatibility facade over the canonical TrustEngine. Older wiring may
ask for a RecommendationEngine; the implementation must still use the same
trust accounting and profile-change contract as the active runtime.
"""

from __future__ import annotations

from typing import Any, Iterable

from nova.autotune.trust_engine import TrustEngine, TrustUpdateResult
from nova.shadow.outcome import ScenarioOutcome


class RecommendationEngine:
    def __init__(self, trust_engine: TrustEngine | None = None) -> None:
        self.trust_engine = trust_engine or TrustEngine()

    def recommend(
        self,
        evidence: Iterable[ScenarioOutcome],
        *,
        target_profile_id: str,
        profile_values: dict[str, Any],
        evidence_ids: list[str] | None = None,
    ) -> TrustUpdateResult:
        return self.trust_engine.build_recommendation(
            target_profile_id=target_profile_id,
            profile_values=profile_values,
            outcomes=evidence,
            evidence_ids=evidence_ids or [],
        )
