"""Analyzer runner with explicit no-echo stage separation."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from nova.analyzers.contracts import AnalysisPackage, AnalyzerContext, BaseAnalyzer
from nova.analyzers.registry import AnalyzerRegistry
from nova.core.evidence import CardStage
from nova.data.models import MarketSnapshot


class AnalyzerRunner:
    def __init__(self, registry: AnalyzerRegistry) -> None:
        self.registry = registry

    def run_raw_pass(
        self,
        *,
        run_id: str,
        cycle_id: str,
        symbol: str,
        timeframe: str,
        profile_id: str,
        parameters: Dict[str, Any] | None = None,
        market_snapshot: MarketSnapshot | None = None,
        market_snapshot_id: Optional[str] = None,
        available_data_ids: Iterable[str] | None = None,
    ) -> List[AnalysisPackage]:
        data_ids = list(available_data_ids) if available_data_ids is not None else _snapshot_data_ids(market_snapshot)
        context = AnalyzerContext(
            run_id=run_id,
            cycle_id=cycle_id,
            symbol=symbol,
            timeframe=timeframe,
            profile_id=profile_id,
            parameters=parameters or {},
            market_snapshot=market_snapshot,
            market_snapshot_id=market_snapshot_id or (market_snapshot.snapshot_id if market_snapshot else None),
            available_data_ids=data_ids,
            stage=CardStage.RAW,
            input_matrix_id=None,
            feedback_depth=0,
        )
        return self._run(self.registry.supports_raw(), context)

    def run_validation_pass(
        self,
        *,
        run_id: str,
        cycle_id: str,
        symbol: str,
        timeframe: str,
        profile_id: str,
        input_matrix_id: str,
        parent_card_ids: Iterable[str] | None = None,
        parameters: Dict[str, Any] | None = None,
        market_snapshot: MarketSnapshot | None = None,
        market_snapshot_id: Optional[str] = None,
        available_data_ids: Iterable[str] | None = None,
    ) -> List[AnalysisPackage]:
        data_ids = list(available_data_ids) if available_data_ids is not None else _snapshot_data_ids(market_snapshot)
        context = AnalyzerContext(
            run_id=run_id,
            cycle_id=cycle_id,
            symbol=symbol,
            timeframe=timeframe,
            profile_id=profile_id,
            parameters=parameters or {},
            market_snapshot=market_snapshot,
            market_snapshot_id=market_snapshot_id or (market_snapshot.snapshot_id if market_snapshot else None),
            available_data_ids=data_ids,
            stage=CardStage.VALIDATION,
            input_matrix_id=input_matrix_id,
            feedback_depth=1,
            parent_card_ids=list(parent_card_ids or []),
        )
        return self._run(self.registry.supports_validation(), context)

    @staticmethod
    def _run(analyzers: Iterable[BaseAnalyzer], context: AnalyzerContext) -> List[AnalysisPackage]:
        return [analyzer.analyze(context) for analyzer in analyzers]


def _snapshot_data_ids(snapshot: MarketSnapshot | None) -> List[str]:
    if snapshot is None:
        return []
    ids = [snapshot.snapshot_id]
    ids.extend(series.series_id for series in snapshot.candles.values())
    if snapshot.orderbook is not None:
        ids.append(snapshot.orderbook.snapshot_id)
    if snapshot.agg_trades is not None:
        ids.append(snapshot.agg_trades.series_id)
    if snapshot.derivatives is not None:
        ids.append(snapshot.derivatives.snapshot_id)
    if snapshot.news is not None:
        ids.append(snapshot.news.batch_id)
    return ids
