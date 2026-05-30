"""CardDeck contracts for acyclic evidence flow.

Cards let analyzers produce rich evidence without turning matrix feedback into
self-confirming statistics. Only cards with explicit rights can seed forecast
fields, adjust zone metadata, request rechecks or affect primary statistics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from nova.analysis.models import EvidenceRef
from nova.core.evidence import CardStage, CardType, EvidenceTier
from nova.core.ids import CARD, new_id


@dataclass(frozen=True)
class CardInfluenceRights:
    can_seed_field: bool = False
    can_adjust_zone_metadata: bool = False
    can_request_recheck: bool = False
    can_affect_decision_context: bool = False
    can_affect_primary_statistics: bool = False


@dataclass(frozen=True)
class EvidenceCard:
    card_type: str
    stage: str
    tier: str
    cycle_id: str
    card_id: str = field(default_factory=lambda: new_id(CARD))
    source_analysis_result_id: Optional[str] = None
    source_analyzer: Optional[str] = None
    input_matrix_id: Optional[str] = None
    feedback_depth: int = 0
    parent_card_ids: List[str] = field(default_factory=list)
    target_zone_ids: List[str] = field(default_factory=list)
    rights: CardInfluenceRights = field(default_factory=CardInfluenceRights)
    evidence_refs: List[EvidenceRef] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def primary_forecast(
        cls,
        cycle_id: str,
        source_analysis_result_id: str,
        source_analyzer: str,
        payload: Dict[str, Any],
        evidence_refs: List[EvidenceRef] | None = None,
    ) -> "EvidenceCard":
        return cls(
            card_type=CardType.FORECAST,
            stage=CardStage.RAW,
            tier=EvidenceTier.PRIMARY,
            cycle_id=cycle_id,
            source_analysis_result_id=source_analysis_result_id,
            source_analyzer=source_analyzer,
            rights=CardInfluenceRights(
                can_seed_field=True,
                can_affect_decision_context=True,
                can_affect_primary_statistics=True,
            ),
            evidence_refs=evidence_refs or [],
            payload=payload,
        )

    @classmethod
    def validation(
        cls,
        cycle_id: str,
        source_analysis_result_id: str,
        source_analyzer: str,
        target_zone_ids: List[str],
        payload: Dict[str, Any],
        input_matrix_id: str,
        parent_card_ids: List[str] | None = None,
    ) -> "EvidenceCard":
        return cls(
            card_type=CardType.VALIDATION,
            stage=CardStage.VALIDATION,
            tier=EvidenceTier.META,
            cycle_id=cycle_id,
            source_analysis_result_id=source_analysis_result_id,
            source_analyzer=source_analyzer,
            input_matrix_id=input_matrix_id,
            feedback_depth=1,
            parent_card_ids=parent_card_ids or [],
            target_zone_ids=target_zone_ids,
            rights=CardInfluenceRights(
                can_adjust_zone_metadata=True,
                can_affect_decision_context=True,
            ),
            payload=payload,
        )

    @classmethod
    def recheck_request(
        cls,
        cycle_id: str,
        target_zone_ids: List[str],
        payload: Dict[str, Any],
        input_matrix_id: str,
        parent_card_ids: List[str] | None = None,
    ) -> "EvidenceCard":
        return cls(
            card_type=CardType.RECHECK_REQUEST,
            stage=CardStage.RECHECK,
            tier=EvidenceTier.META,
            cycle_id=cycle_id,
            input_matrix_id=input_matrix_id,
            feedback_depth=1,
            parent_card_ids=parent_card_ids or [],
            target_zone_ids=target_zone_ids,
            rights=CardInfluenceRights(
                can_request_recheck=True,
                can_affect_decision_context=True,
            ),
            payload=payload,
        )


@dataclass(frozen=True)
class CardDeck:
    cycle_id: str
    cards: List[EvidenceCard] = field(default_factory=list)

    def primary_field_cards(self) -> List[EvidenceCard]:
        return [
            card
            for card in self.cards
            if card.tier == EvidenceTier.PRIMARY
            and card.stage == CardStage.RAW
            and card.feedback_depth == 0
            and card.rights.can_seed_field
        ]

