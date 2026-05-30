"""Forecast matrix engine skeleton.

Aggregates sparse forecast contributions into top price-time zones.
"""

from __future__ import annotations

from typing import Iterable

from nova.matrix.models import ForecastContribution, ForecastMatrix


class ForecastMatrixEngine:
    def build(self, cycle_id: str, symbol: str, contributions: Iterable[ForecastContribution]) -> ForecastMatrix:
        raise NotImplementedError("Aggregate contributions into forecast zones")

