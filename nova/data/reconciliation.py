"""Candle continuity and reconciliation helpers."""

from __future__ import annotations

from datetime import datetime
from typing import List, Tuple

from nova.data.models import CandleSeries, DataQualityReport
from nova.data.synthetic_tf import timeframe_to_minutes


class TimeframeReconciler:
    def detect_gaps(self, series: CandleSeries) -> List[Tuple[str, str]]:
        expected_sec = timeframe_to_minutes(series.timeframe) * 60
        gaps: List[Tuple[str, str]] = []
        ordered = sorted(series.candles, key=lambda candle: candle.open_time)
        for previous, current in zip(ordered, ordered[1:]):
            delta = _parse_iso(current.open_time).timestamp() - _parse_iso(previous.open_time).timestamp()
            if delta > expected_sec * 1.5:
                gaps.append((previous.open_time, current.open_time))
        return gaps

    def evaluate_candle_series_quality(self, series: CandleSeries, expected_min_count: int = 1) -> DataQualityReport:
        gaps = self.detect_gaps(series)
        completeness = min(1.0, series.count / max(1, expected_min_count))
        is_usable = series.count >= expected_min_count and not gaps
        issue_codes: List[str] = []
        if series.count < expected_min_count:
            issue_codes.append("insufficient_candles")
        if gaps:
            issue_codes.append("candle_gaps")
        return DataQualityReport(
            is_usable=is_usable,
            score=max(0.0, completeness - (0.1 * len(gaps))),
            completeness=completeness,
            gap_count=len(gaps),
            issue_codes=issue_codes,
            payload={"gaps": gaps, "expected_min_count": expected_min_count},
        )

    def reconcile(self, series: CandleSeries, expected_min_count: int = 1) -> DataQualityReport:
        return self.evaluate_candle_series_quality(series, expected_min_count=expected_min_count)


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
