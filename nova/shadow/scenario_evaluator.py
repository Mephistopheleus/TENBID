"""Single calculation engine for all alternative scenarios."""

from nova.shadow.outcome import ScenarioOutcome
from nova.shadow.scenario import ScenarioRequest


class ScenarioEvaluator:
    def evaluate(self, request: ScenarioRequest) -> ScenarioOutcome:
        raise NotImplementedError("Evaluate scenario using candles, intrabar resolver, costs and trailing rules")

