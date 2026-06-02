"""Generates parameter and behavior hypotheses from MarketEpisode dynamics.

Laboratory must look for both overtrusted and undertrusted evidence/context:
where NOVA trusted too much, and where it rejected or discounted something that
later proved useful. It dispatches checks; ScenarioEvaluator resolves outcomes.
"""

from __future__ import annotations

from nova.episodes.dynamics_features import DynamicsFeatureExtractor
from nova.episodes.models import MarketEpisode


class HypothesisGenerator:
    def __init__(self, extractor: DynamicsFeatureExtractor | None = None) -> None:
        self.extractor = extractor or DynamicsFeatureExtractor()

    def generate(self, episode: MarketEpisode) -> list[dict[str, object]]:
        dynamics = self.extractor.extract(episode)
        extra = dynamics.extra
        hypotheses: list[dict[str, object]] = []
        outcome = extra.get("outcome_result")
        hard_blocks = [block for group in extra.get("risk_hard_blocks", []) if isinstance(group, list) for block in group]
        if outcome == "OBSERVED_WIN" and hard_blocks:
            hypotheses.append(
                {
                    "source_id": episode.episode_id,
                    "purpose": "undertrusted_rejected_winner_check",
                    "related_plan_id": episode.related_plan_id,
                    "signals": {
                        "hard_blocks": hard_blocks,
                        "net_expected_edge_pct": extra.get("net_expected_edge_pct"),
                        "rr_ratio": extra.get("rr_ratio"),
                        "outcome_net_pnl_pct": extra.get("outcome_net_pnl_pct"),
                    },
                }
            )
        if outcome == "OBSERVED_LOSS" and not hard_blocks:
            hypotheses.append(
                {
                    "source_id": episode.episode_id,
                    "purpose": "overtrusted_approved_or_unblocked_loser_check",
                    "related_plan_id": episode.related_plan_id,
                    "signals": {
                        "confidence": extra.get("confidence"),
                        "net_expected_edge_pct": extra.get("net_expected_edge_pct"),
                        "rr_ratio": extra.get("rr_ratio"),
                        "outcome_net_pnl_pct": extra.get("outcome_net_pnl_pct"),
                    },
                }
            )
        if dynamics.liquidity_stability == 0.0:
            hypotheses.append(
                {
                    "source_id": episode.episode_id,
                    "purpose": "liquidity_context_gap_check",
                    "related_plan_id": episode.related_plan_id,
                    "signals": {"liquidity_stability": dynamics.liquidity_stability},
                }
            )
        return hypotheses
