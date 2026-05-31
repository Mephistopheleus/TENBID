"""Explicit analyzer registry.

NOVA intentionally starts with manual registration. That keeps analyzer loading
auditable while the architecture is still being hardened.
"""

from __future__ import annotations

from typing import Dict, Iterable, List

from nova.analyzers.contracts import BaseAnalyzer, AnalyzerManifest


class AnalyzerRegistry:
    def __init__(self, analyzers: Iterable[BaseAnalyzer] | None = None) -> None:
        self._analyzers: Dict[str, BaseAnalyzer] = {}
        for analyzer in analyzers or []:
            self.register(analyzer)

    def register(self, analyzer: BaseAnalyzer) -> None:
        name = analyzer.manifest.name
        if name in self._analyzers:
            raise ValueError(f"Analyzer already registered: {name}")
        self._analyzers[name] = analyzer

    def get(self, name: str) -> BaseAnalyzer:
        try:
            return self._analyzers[name]
        except KeyError as exc:
            raise KeyError(f"Unknown analyzer: {name}") from exc

    def all(self) -> List[BaseAnalyzer]:
        return list(self._analyzers.values())

    def manifests(self) -> Dict[str, AnalyzerManifest]:
        return {name: analyzer.manifest for name, analyzer in self._analyzers.items()}

    def supports_raw(self) -> List[BaseAnalyzer]:
        return [analyzer for analyzer in self._analyzers.values() if analyzer.manifest.supports_raw]

    def supports_validation(self) -> List[BaseAnalyzer]:
        return [analyzer for analyzer in self._analyzers.values() if analyzer.manifest.supports_validation]

    def supports_recheck(self) -> List[BaseAnalyzer]:
        return [analyzer for analyzer in self._analyzers.values() if analyzer.manifest.supports_recheck]

