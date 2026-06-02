"""Extract entry/lifecycle dynamics from MarketEpisode payloads."""

from __future__ import annotations

from nova.episodes.models import DynamicsContext, MarketEpisode


class DynamicsFeatureExtractor:
    def extract(self, episode: MarketEpisode) -> DynamicsContext:
        plan = episode.payload.get("plan", {}) if isinstance(episode.payload, dict) else {}
        events = episode.payload.get("events", []) if isinstance(episode.payload, dict) else []
        outcomes = episode.payload.get("outcomes", []) if isinstance(episode.payload, dict) else []
        risk_events = [event for event in events if event.get("event_type") == "RISK_DECISION_CREATED"]
        executor_events = [event for event in events if event.get("event_type") == "EXECUTOR_RESULT_RECORDED"]
        final_outcome = outcomes[-1] if outcomes else {}
        return DynamicsContext(
            episode_id=episode.episode_id,
            lookback_min=self._duration_min(episode),
            price_velocity=None,
            volatility_trend=None,
            volume_trend=None,
            matrix_probability_slope=None,
            confidence_slope=None,
            state_conflict_trend=None,
            spread_trend=None,
            liquidity_stability=1.0 if self._orderbook_available(events) else 0.0,
            extra={
                "plan_id": episode.related_plan_id,
                "decision": plan.get("decision"),
                "confidence": plan.get("confidence"),
                "net_expected_edge_pct": plan.get("net_expected_edge_pct"),
                "rr_ratio": plan.get("rr_ratio"),
                "risk_hard_blocks": [self._payload(event).get("hard_blocks", []) for event in risk_events],
                "executor_statuses": [self._payload(event).get("status") for event in executor_events],
                "outcome_result": final_outcome.get("result"),
                "outcome_resolution_method": final_outcome.get("resolution_method"),
                "outcome_net_pnl_pct": final_outcome.get("net_pnl_pct"),
            },
        )

    @staticmethod
    def _payload(event: object) -> dict[str, object]:
        if isinstance(event, dict) and isinstance(event.get("payload"), dict):
            return event["payload"]
        return {}

    @staticmethod
    def _orderbook_available(events: list[object]) -> bool:
        for event in events:
            payload = DynamicsFeatureExtractor._payload(event)
            if payload.get("liquidity_state") == "orderbook_available":
                return True
            if payload.get("state_liquidity_state") == "orderbook_available":
                return True
        return False

    @staticmethod
    def _duration_min(episode: MarketEpisode) -> int:
        return max(1, len(episode.event_ids))
