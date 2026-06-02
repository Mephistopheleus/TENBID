"""Select market episodes for laboratory analysis."""

from __future__ import annotations

from nova.core.history_db import HistoryDB
from nova.episodes.episode_builder import EpisodeBuilder
from nova.episodes.models import MarketEpisode


class EpisodeSampler:
    def __init__(self, history_db: HistoryDB) -> None:
        self.history_db = history_db

    def sample(self, *, limit: int = 50) -> list[MarketEpisode]:
        with self.history_db._connect() as conn:  # noqa: SLF001 - read-only sampling from NOVA memory.
            rows = conn.execute(
                "SELECT plan_id FROM trade_plans ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        builder = EpisodeBuilder(self.history_db)
        episodes: list[MarketEpisode] = []
        for row in rows:
            plan_id = row["plan_id"]
            if not plan_id:
                continue
            episode = builder.build_for_plan(str(plan_id))
            if episode is not None:
                episodes.append(episode)
        return episodes
