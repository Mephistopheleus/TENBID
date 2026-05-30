"""Extracts EntryDynamics and LifecycleDynamics from market episodes."""

class DynamicsFeatureExtractor:
    def extract(self, episode: object) -> object:
        raise NotImplementedError

