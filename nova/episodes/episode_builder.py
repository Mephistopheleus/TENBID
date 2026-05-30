"""Builds MarketEpisode objects from EventLog windows."""

class EpisodeBuilder:
    def build_for_plan(self, plan_id: str) -> object:
        raise NotImplementedError

