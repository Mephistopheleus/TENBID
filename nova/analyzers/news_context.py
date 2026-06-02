"""Canonical NOVA news/context analyzer."""

from __future__ import annotations

from nova.analysis.models import EvidenceRef
from nova.analyzers.common import build_package, clamp, evidence_refs_for_snapshot, no_data_package
from nova.analyzers.contracts import AnalysisPackage, AnalyzerContext, AnalyzerManifest
from nova.core.evidence import CardType
from nova.data.synthetic_tf import timeframe_to_minutes


class NewsContextAnalyzer:
    manifest = AnalyzerManifest(
        name="news_context_analyzer",
        version="0.1.0",
        description="Observes available news/event risk context without creating market signals.",
        dependency_group="news_context",
        required_inputs=["MarketSnapshot.news"],
        supported_timeframes=["5m"],
        output_card_types=[CardType.STATE],
        parameter_names=["news_horizon_bars"],
    )

    def analyze(self, context: AnalyzerContext) -> AnalysisPackage:
        snapshot = context.market_snapshot
        if snapshot is None:
            return no_data_package(self.manifest, context, "missing_market_snapshot")
        batch = snapshot.news
        if batch is None:
            return no_data_package(self.manifest, context, "news_not_loaded")
        relevant = [
            item for item in batch.items
            if not item.symbols or context.symbol in item.symbols or snapshot.primary_symbol in item.symbols
        ]
        if not relevant:
            return no_data_package(self.manifest, context, "no_relevant_news_items")
        topic_counts: dict[str, int] = {}
        for item in relevant:
            for topic in item.topics:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1
        avg_sentiment = sum(item.sentiment_score for item in relevant) / len(relevant)
        max_impact = max(item.impact_score for item in relevant)
        event_risk = clamp((abs(avg_sentiment) * 0.35) + (max_impact * 0.55) + min(len(relevant) / 20.0, 0.10))
        confidence = clamp(0.2 + min(len(relevant) / 10.0, 0.30) + max_impact * 0.35 + batch.quality.score * 0.15, 0.1, 0.9)
        payload = {
            "phenomenon": "news_event_context",
            "relevant_item_count": len(relevant),
            "average_sentiment_observation": avg_sentiment,
            "max_impact_score": max_impact,
            "event_risk_observation": event_risk,
            "topic_counts": topic_counts,
            "top_items": [
                {
                    "item_id": item.item_id,
                    "title": item.title,
                    "source_name": item.source_name,
                    "published_at": item.published_at,
                    "sentiment_score": item.sentiment_score,
                    "impact_score": item.impact_score,
                    "topics": item.topics,
                    "url": item.url,
                }
                for item in relevant[:8]
            ],
            "donor_legacy_idea": "freshness/topic/impact_context_without_news_direction_signal",
        }
        horizon_min = max(1, int(context.parameters.get("news_horizon_bars", 12))) * timeframe_to_minutes(context.timeframe)
        return build_package(
            manifest=self.manifest,
            context=context,
            payload=payload,
            confidence=confidence,
            quality=min(snapshot.quality.score, batch.quality.score),
            evidence_refs=evidence_refs_for_snapshot(
                snapshot,
                extra=[EvidenceRef("news_batch", batch.batch_id, "News batch available in MarketSnapshot.")],
            ),
            forecast_specs=[],
            state_type="news_event_context",
            state_value=payload,
            state_severity="WARN" if event_risk >= 0.65 else "INFO",
            ttl_sec=max(60, horizon_min * 60),
        )
