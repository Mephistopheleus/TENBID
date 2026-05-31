"""Analyzer runner with explicit no-echo stage separation."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from nova.analyzers.contracts import AnalysisPackage, AnalyzerContext, BaseAnalyzer
from nova.analyzers.registry import AnalyzerRegistry
from nova.core.evidence import CardStage


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
        market_snapshot_id: Optional[str] = None,
        available_data_ids: Iterable[str] | None = None,
    ) -> List[AnalysisPackage]:
        context = AnalyzerContext(
            run_id=run_id,
            cycle_id=cycle_id,
            symbol=symbol,
            timeframe=timeframe,
            profile_id=profile_id,
            parameters=parameters or {},
            market_snapshot_id=market_snapshot_id,
            available_data_ids=list(available_data_ids or []),
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
        market_snapshot_id: Optional[str] = None,
        available_data_ids: Iterable[str] | None = None,
    ) -> List[AnalysisPackage]:
        context = AnalyzerContext(
            run_id=run_id,
            cycle_id=cycle_id,
            symbol=symbol,
            timeframe=timeframe,
            profile_id=profile_id,
            parameters=parameters or {},
            market_snapshot_id=market_snapshot_id,
            available_data_ids=list(available_data_ids or []),
            stage=CardStage.VALIDATION,
            input_matrix_id=input_matrix_id,
            feedback_depth=1,
            parent_card_ids=list(parent_card_ids or []),
        )
        return self._run(self.registry.supports_validation(), context)

    @staticmethod
    def _run(analyzers: Iterable[BaseAnalyzer], context: AnalyzerContext) -> List[AnalysisPackage]:
        return [analyzer.analyze(context) for analyzer in analyzers]

