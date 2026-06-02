"""Canonical NOVA orderbook/liquidity analyzer."""

from __future__ import annotations

from nova.analysis.models import EvidenceRef
from nova.analyzers.common import build_package, clamp, evidence_refs_for_snapshot, no_data_package, safe_div
from nova.analyzers.contracts import AnalysisPackage, AnalyzerContext, AnalyzerManifest
from nova.core.evidence import CardType
from nova.data.synthetic_tf import timeframe_to_minutes


class OrderbookLiquidityAnalyzer:
    manifest = AnalyzerManifest(
        name="orderbook_liquidity_analyzer",
        version="0.1.0",
        description="Observes spread, near-book imbalance, walls and thin liquidity zones.",
        dependency_group="orderbook_liquidity",
        required_inputs=["MarketSnapshot.orderbook"],
        supported_timeframes=["5m"],
        output_card_types=[CardType.FORECAST, CardType.STATE],
        parameter_names=["orderbook_near_bps", "orderbook_wall_factor", "orderbook_horizon_bars"],
    )

    def analyze(self, context: AnalyzerContext) -> AnalysisPackage:
        snapshot = context.market_snapshot
        if snapshot is None:
            return no_data_package(self.manifest, context, "missing_market_snapshot")
        orderbook = snapshot.orderbook
        if orderbook is None:
            return no_data_package(self.manifest, context, "orderbook_not_loaded")
        if not orderbook.bids or not orderbook.asks:
            return no_data_package(self.manifest, context, "empty_orderbook")
        best_bid = orderbook.best_bid()
        best_ask = orderbook.best_ask()
        if best_bid is None or best_ask is None or best_bid.price <= 0.0 or best_ask.price < best_bid.price:
            return no_data_package(self.manifest, context, "invalid_orderbook_top")

        mid = (best_bid.price + best_ask.price) / 2.0
        near_bps = max(1.0, float(context.parameters.get("orderbook_near_bps", 25.0)))
        wall_factor = max(1.1, float(context.parameters.get("orderbook_wall_factor", 3.0)))
        horizon_bars = max(1, int(context.parameters.get("orderbook_horizon_bars", 2)))
        near_distance = mid * near_bps / 10000.0
        near_bids = [level for level in orderbook.bids if mid - level.price <= near_distance]
        near_asks = [level for level in orderbook.asks if level.price - mid <= near_distance]
        bid_qty = sum(level.quantity for level in near_bids)
        ask_qty = sum(level.quantity for level in near_asks)
        imbalance = safe_div(bid_qty - ask_qty, bid_qty + ask_qty, 0.0)
        spread_pct = safe_div(best_ask.price - best_bid.price, mid, 0.0) * 100.0
        all_quantities = [level.quantity for level in [*orderbook.bids, *orderbook.asks] if level.quantity > 0.0]
        average_qty = sum(all_quantities) / max(1, len(all_quantities))
        bid_walls = [level for level in orderbook.bids if level.quantity >= average_qty * wall_factor]
        ask_walls = [level for level in orderbook.asks if level.quantity >= average_qty * wall_factor]
        nearest_bid_wall = max(bid_walls, key=lambda level: level.price, default=None)
        nearest_ask_wall = min(ask_walls, key=lambda level: level.price, default=None)
        liquidity_score = clamp(1.0 - min(spread_pct / 0.25, 1.0))
        confidence = clamp(0.25 + abs(imbalance) * 0.35 + liquidity_score * 0.25 + min(len(bid_walls) + len(ask_walls), 6) * 0.025, 0.1, 0.9)
        low = nearest_bid_wall.price if nearest_bid_wall is not None else best_bid.price
        high = nearest_ask_wall.price if nearest_ask_wall is not None else best_ask.price

        payload = {
            "phenomenon": "visible_liquidity_topology",
            "mid_price": mid,
            "spread_pct": spread_pct,
            "near_book_bps": near_bps,
            "near_bid_qty": bid_qty,
            "near_ask_qty": ask_qty,
            "near_book_imbalance": imbalance,
            "liquidity_score": liquidity_score,
            "bid_walls": [{"price": level.price, "quantity": level.quantity} for level in bid_walls[:8]],
            "ask_walls": [{"price": level.price, "quantity": level.quantity} for level in ask_walls[:8]],
            "execution_risk_observation": "spread_and_visible_depth_only_not_fill_prediction",
            "donor_legacy_idea": "imbalance/walls/SR_adjustment_without_dominant_signal",
        }
        horizon_min = horizon_bars * timeframe_to_minutes(context.timeframe)
        return build_package(
            manifest=self.manifest,
            context=context,
            payload=payload,
            confidence=confidence,
            quality=min(snapshot.quality.score, orderbook.quality.score),
            evidence_refs=evidence_refs_for_snapshot(
                snapshot,
                extra=[EvidenceRef("orderbook_snapshot", orderbook.snapshot_id, "Visible orderbook snapshot.")],
            ),
            forecast_specs=[
                {
                    "price_low": low,
                    "price_high": high,
                    "horizon_min": horizon_min,
                    "probability": confidence,
                    "confidence": confidence,
                    "direction": "LIQUIDITY_CONTEXT",
                    "phenomenon": "visible_liquidity_topology",
                    "field_shape": "wall_to_wall_band",
                    "weight": 0.6,
                }
            ],
            state_type="liquidity_context",
            state_value=payload,
            state_severity="WARN" if spread_pct > 0.20 else "INFO",
            ttl_sec=max(60, horizon_min * 60),
        )
