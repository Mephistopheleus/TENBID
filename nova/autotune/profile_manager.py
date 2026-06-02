"""Validate and apply Autotuner recommendations to active_profile.json.

The profile manager is the only component allowed to mutate the active
Autotuner-owned profile. It deliberately cannot touch secrets, trading mode,
LIVE unlocks or owner safety locks because those values are outside
active_profile.json and outside the allowed parameter registry below.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nova.autotune.models import AutotuneRecommendation


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    value_type: type
    minimum: float | int | None = None
    maximum: float | int | None = None
    autotune_enabled: bool = True


@dataclass(frozen=True)
class ProfileApplyResult:
    status: str
    recommendation_id: str
    applied_changes: dict[str, object] = field(default_factory=dict)
    rejected_changes: dict[str, str] = field(default_factory=dict)
    profile_path: str | None = None
    rollback_path: str | None = None
    reason: str | None = None


class ProfileManager:
    """Applies validated recommendations atomically to the active profile."""

    _SPECS: dict[str, ParameterSpec] = {
        "market_structure_analyzer_trust_points": ParameterSpec(
            "market_structure_analyzer_trust_points", float, minimum=0.0, maximum=0.9
        ),
        "shadow_outcome_sample_count": ParameterSpec(
            "shadow_outcome_sample_count", int, minimum=0, maximum=1_000_000
        ),
        "target_rr_min": ParameterSpec("target_rr_min", float, minimum=0.8, maximum=3.0),
        "min_net_edge_pct": ParameterSpec("min_net_edge_pct", float, minimum=0.05, maximum=1.0),
    }

    def __init__(self, profile_path: str | Path) -> None:
        self.profile_path = Path(profile_path)

    def apply_recommendation(self, recommendation: AutotuneRecommendation) -> ProfileApplyResult:
        profile = self._read_profile()
        if recommendation.target_profile_id != str(profile.get("profile_id")):
            return ProfileApplyResult(
                status="rejected",
                recommendation_id=recommendation.recommendation_id,
                profile_path=str(self.profile_path),
                reason="target_profile_id_mismatch",
            )
        if not bool(profile.get("autotuner_managed")):
            return ProfileApplyResult(
                status="rejected",
                recommendation_id=recommendation.recommendation_id,
                profile_path=str(self.profile_path),
                reason="profile_not_autotuner_managed",
            )

        applied: dict[str, object] = {}
        rejected: dict[str, str] = {}
        updated = dict(profile)
        for name, raw_value in recommendation.parameter_changes.items():
            spec = self._SPECS.get(name)
            if spec is None or not spec.autotune_enabled:
                rejected[name] = "parameter_not_registered_for_autotune"
                continue
            value = self._coerce_value(raw_value, spec)
            if value is None:
                rejected[name] = "invalid_value_type"
                continue
            if spec.minimum is not None and value < spec.minimum:
                rejected[name] = "below_allowed_minimum"
                continue
            if spec.maximum is not None and value > spec.maximum:
                rejected[name] = "above_allowed_maximum"
                continue
            updated[name] = value
            applied[name] = value

        if not applied:
            return ProfileApplyResult(
                status="rejected",
                recommendation_id=recommendation.recommendation_id,
                rejected_changes=rejected,
                profile_path=str(self.profile_path),
                reason="no_valid_parameter_changes",
            )

        updated["profile_source"] = "autotuner"
        rollback_path = self._rollback_path(recommendation.recommendation_id)
        rollback_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.profile_path, rollback_path)
        self._atomic_write(updated)
        return ProfileApplyResult(
            status="applied" if not rejected else "partially_applied",
            recommendation_id=recommendation.recommendation_id,
            applied_changes=applied,
            rejected_changes=rejected,
            profile_path=str(self.profile_path),
            rollback_path=str(rollback_path),
        )

    def _read_profile(self) -> dict[str, Any]:
        with self.profile_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _atomic_write(self, profile: dict[str, Any]) -> None:
        tmp_path = self.profile_path.with_suffix(self.profile_path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(profile, handle, indent=2, sort_keys=False)
            handle.write("\n")
        os.replace(tmp_path, self.profile_path)

    def _rollback_path(self, recommendation_id: str) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        return self.profile_path.parent / "profile_rollbacks" / f"{stamp}_{recommendation_id}.json"

    @staticmethod
    def _coerce_value(value: object, spec: ParameterSpec) -> int | float | None:
        try:
            if spec.value_type is int:
                if isinstance(value, bool):
                    return None
                return int(value)
            if spec.value_type is float:
                if isinstance(value, bool):
                    return None
                return float(value)
        except (TypeError, ValueError):
            return None
        return None
