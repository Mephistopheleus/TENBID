"""Universal scenario request contract.

ScenarioEvaluator must not care whether the request comes from HOLD shadow,
forbidden-candidate shadow, laboratory, matrix validation or a parameter sweep.
The source_type/tags carry the reason: especially whether we are checking that a
blocked candidate was correctly blocked or was too strictly rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from nova.core.ids import SCENARIO, new_id


@dataclass(frozen=True)
class ScenarioRequest:
    source_type: str
    source_id: str
    symbol: str
    trade_plan_id: Optional[str]
    episode_id: Optional[str]
    evaluation_window_min: int
    parameter_variant: Dict[str, object] = field(default_factory=dict)
    tags: Dict[str, str] = field(default_factory=dict)
    scenario_id: str = field(default_factory=lambda: new_id(SCENARIO))


class ScenarioSource:
    REAL_EXECUTION = "REAL_EXECUTION"
    HOLD_SHADOW = "HOLD_SHADOW"
    SHADOW_FORBIDDEN = "SHADOW_FORBIDDEN"
    SHADOW_ALTERNATIVE = "SHADOW_ALTERNATIVE"
    LAB_EXPERIMENT = "LAB_EXPERIMENT"
    LAB_OVERTRUSTED_CHECK = "LAB_OVERTRUSTED_CHECK"
    LAB_UNDERTRUSTED_CHECK = "LAB_UNDERTRUSTED_CHECK"
    MATRIX_VALIDATION = "MATRIX_VALIDATION"
    PARAMETER_SWEEP = "PARAMETER_SWEEP"
