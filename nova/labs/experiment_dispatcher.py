"""Dispatches lab hypotheses as ScenarioRequest to ScenarioEvaluator."""

class ExperimentDispatcher:
    def dispatch(self, hypothesis: object) -> object:
        raise NotImplementedError

