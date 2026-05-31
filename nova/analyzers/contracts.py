"""Analyzer foundation contracts.

Future analyzers plug into NOVA through this small interface. They can analyze
any kind of market phenomenon internally, but they must return a standardized
AnalysisPackage so Matrix, Shadow, Laboratory and Autotuner can reason over the
result without knowing analyzer internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from nova.analysis.models import AnalysisResult, StateContribution
from nova.cards.models import CardDeck
from nova.core.evidence import CardStage
from nova.data.models import MarketSnapshot
from nova.matrix.models import ForecastContribution


@dataclass(frozen=True)
class AnalyzerManifest:
    name: str
    version: str
    description: str = ""
    dependency_group: str = "unknown"
    required_inputs: List[str] = field(default_factory=list)
    supported_timeframes: List[str] = field(default_factory=list)
    output_card_types: List[str] = field(default_factory=list)
    parameter_names: List[str] = field(default_factory=list)
    supports_raw: bool = True
    supports_validation: bool = False
    supports_recheck: bool = False


@dataclass(frozen=True)
class AnalyzerContext:
    run_id: str
    cycle_id: str
    symbol: str
    timeframe: str
    profile_id: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    market_snapshot: Optional[MarketSnapshot] = None
    market_snapshot_id: Optional[str] = None
    available_data_ids: List[str] = field(default_factory=list)
    stage: str = CardStage.RAW
    input_matrix_id: Optional[str] = None
    feedback_depth: int = 0
    parent_card_ids: List[str] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalysisPackage:
    analysis_result: AnalysisResult
    card_deck: CardDeck
    forecast_contributions: List[ForecastContribution] = field(default_factory=list)
    state_contributions: List[StateContribution] = field(default_factory=list)

    def all_card_ids(self) -> List[str]:
        return [card.card_id for card in self.card_deck.cards]

    def all_contribution_ids(self) -> List[str]:
        return [item.contribution_id for item in self.forecast_contributions]


@runtime_checkable
class BaseAnalyzer(Protocol):
    manifest: AnalyzerManifest

    def analyze(self, context: AnalyzerContext) -> AnalysisPackage:
        """Return a standardized package for the requested analysis stage."""
