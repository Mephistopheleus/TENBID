"""Dispatches lab hypotheses as ScenarioRequest to ScenarioEvaluator.

Lab requests must be tagged by purpose, for example overtrusted-check,
undertrusted-check, forbidden-rule-check or parameter-sweep. Tags keep Autotuner
from mixing laboratory evidence with runtime facts.
"""

class ExperimentDispatcher:
    def dispatch(self, hypothesis: object) -> object:
        raise NotImplementedError
