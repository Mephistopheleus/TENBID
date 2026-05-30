"""Registry of tunable parameters.

New modules can add tunable parameters without changing Autotuner internals if
they register ParameterSpec and include parameters_used in AnalysisResult.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    owner: str
    value_type: str
    default: Any
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step: Optional[float] = None
    autotune_enabled: bool = True
    risk_level: str = "low"
    description: str = ""


class ParameterRegistry:
    def __init__(self, specs: Iterable[ParameterSpec] | None = None) -> None:
        self._specs: Dict[str, ParameterSpec] = {}
        for spec in specs or []:
            self.register(spec)

    def register(self, spec: ParameterSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"Parameter already registered: {spec.name}")
        self._specs[spec.name] = spec

    def get(self, name: str) -> ParameterSpec:
        try:
            return self._specs[name]
        except KeyError as exc:
            raise KeyError(f"Unknown parameter: {name}") from exc

    def all(self) -> Dict[str, ParameterSpec]:
        return dict(self._specs)

    def autotunable(self) -> Dict[str, ParameterSpec]:
        return {name: spec for name, spec in self._specs.items() if spec.autotune_enabled}


DEFAULT_PARAMETER_SPECS = [
    ParameterSpec(
        name="confidence_threshold",
        owner="decision",
        value_type="float",
        default=0.70,
        min_value=0.50,
        max_value=0.90,
        step=0.01,
        risk_level="medium",
        description="Minimum decision confidence before execution candidates are allowed.",
    ),
    ParameterSpec(
        name="matrix_dominance_threshold",
        owner="matrix",
        value_type="float",
        default=0.65,
        min_value=0.50,
        max_value=0.90,
        step=0.01,
        risk_level="medium",
        description="Minimum dominance required from ForecastMatrix top scenario.",
    ),
    ParameterSpec(
        name="min_net_edge_pct",
        owner="risk",
        value_type="float",
        default=0.12,
        min_value=0.00,
        max_value=1.00,
        step=0.01,
        risk_level="high",
        description="Minimum expected net edge after commission, spread and slippage.",
    ),
]


def default_registry() -> ParameterRegistry:
    return ParameterRegistry(DEFAULT_PARAMETER_SPECS)

