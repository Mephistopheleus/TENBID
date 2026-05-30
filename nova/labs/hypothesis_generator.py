"""Generates parameter and behavior hypotheses from MarketEpisode dynamics."""

class HypothesisGenerator:
    def generate(self, episode: object) -> list[object]:
        raise NotImplementedError

