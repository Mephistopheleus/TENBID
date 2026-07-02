"""Collects tagged evidence from real, shadow, lab and matrix validation outcomes."""

from __future__ import annotations

from typing import Dict, Optional

from nova.autotune.models import AutotuneEvidence, AutotuneEvidenceSource


class EvidenceCollector:
    def collect_feedback(
        self,
        *,
        source_type: str,
        source_weight: float,
        profile_id: str,
        parameter_snapshot: Dict[str, object],
        observations: Dict[str, object],
        plan_id: Optional[str] = None,
        scenario_id: Optional[str] = None,
        risk_decision_id: Optional[str] = None,
        executor_result_id: Optional[str] = None,
    ) -> AutotuneEvidence:
        return AutotuneEvidence(
            source_type=source_type,
            source_weight=source_weight,
            profile_id=profile_id,
            plan_id=plan_id,
            scenario_id=scenario_id,
            risk_decision_id=risk_decision_id,
            executor_result_id=executor_result_id,
            parameter_snapshot=parameter_snapshot,
            observations=observations,
        )

    def collect_real_exchange(
        self,
        *,
        profile_id: str,
        parameter_snapshot: Dict[str, object],
        observations: Dict[str, object],
        plan_id: Optional[str] = None,
        scenario_id: Optional[str] = None,
        risk_decision_id: Optional[str] = None,
        executor_result_id: Optional[str] = None,
    ) -> AutotuneEvidence:
        return self.collect_feedback(
            source_type=AutotuneEvidenceSource.REAL_EXCHANGE,
            source_weight=1.0,
            profile_id=profile_id,
            plan_id=plan_id,
            scenario_id=scenario_id,
            risk_decision_id=risk_decision_id,
            executor_result_id=executor_result_id,
            parameter_snapshot=parameter_snapshot,
            observations={"minimum_sample_before_tuning": 50, **observations},
        )
