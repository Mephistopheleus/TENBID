"""Generates parameter and behavior hypotheses from MarketEpisode dynamics.

Laboratory must look for both overtrusted and undertrusted evidence/context:
where NOVA trusted too much, and where it rejected or discounted something that
later proved useful. It dispatches checks; ScenarioEvaluator resolves outcomes.
"""

class HypothesisGenerator:
    def generate(self, episode: object) -> list[object]:
        raise NotImplementedError
