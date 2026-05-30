"""Pre/post matrix validation helpers."""

from __future__ import annotations

from collections.abc import Iterable

from nova.cards.models import CardDeck
from nova.core.evidence import CardStage, EvidenceTier
from nova.matrix.models import ForecastContribution


class MatrixValidator:
    def validate_primary_contributions(
        self,
        contributions: Iterable[ForecastContribution],
        matrix_id: str | None = None,
    ) -> None:
        """Ensure a primary matrix is built only from raw evidence.

        Matrix-assisted revisions and validations may enrich a reconciled layer,
        but they must not seed or reinforce the same primary matrix.
        """
        for contribution in contributions:
            if contribution.stage != CardStage.RAW:
                raise ValueError(
                    f"Primary matrix cannot use non-raw contribution {contribution.contribution_id}"
                )
            if contribution.evidence_tier != EvidenceTier.PRIMARY:
                raise ValueError(
                    f"Primary matrix cannot use non-primary contribution {contribution.contribution_id}"
                )
            if contribution.feedback_depth != 0:
                raise ValueError(
                    f"Primary matrix cannot use feedback contribution {contribution.contribution_id}"
                )
            if matrix_id is not None and contribution.input_matrix_id == matrix_id:
                raise ValueError(
                    f"Primary matrix cannot consume its own reflected contribution {contribution.contribution_id}"
                )

    def validate_primary_cards(self, deck: CardDeck, matrix_id: str | None = None) -> None:
        """Ensure field-seeding cards are raw primary cards only."""
        for card in deck.cards:
            if not card.rights.can_seed_field:
                continue
            if card.stage != CardStage.RAW:
                raise ValueError(f"Field-seeding card must be raw: {card.card_id}")
            if card.tier != EvidenceTier.PRIMARY:
                raise ValueError(f"Field-seeding card must be primary: {card.card_id}")
            if card.feedback_depth != 0:
                raise ValueError(f"Field-seeding card cannot be feedback-derived: {card.card_id}")
            if matrix_id is not None and card.input_matrix_id == matrix_id:
                raise ValueError(f"Field-seeding card cannot reflect the same matrix: {card.card_id}")

    def validate_pre_matrix(self) -> object:
        return True

    def validate_post_matrix(self) -> object:
        return True
