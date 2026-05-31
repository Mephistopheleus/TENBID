"""Data access policy scheduler.

Controls REST/WS usage, orderbook TTL and intrabar replay budgets.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic


@dataclass(frozen=True)
class DataSchedulerPolicy:
    orderbook_ttl_sec: float = 10.0
    reconcile_interval_sec: float = 60.0


class DataScheduler:
    def __init__(self, policy: DataSchedulerPolicy | None = None) -> None:
        self.policy = policy or DataSchedulerPolicy()
        self._last_orderbook_fetch: float | None = None
        self._last_reconcile: float | None = None

    def should_fetch_orderbook(self) -> bool:
        return self._elapsed(self._last_orderbook_fetch) >= self.policy.orderbook_ttl_sec

    def mark_orderbook_fetched(self) -> None:
        self._last_orderbook_fetch = monotonic()

    def should_reconcile(self) -> bool:
        return self._elapsed(self._last_reconcile) >= self.policy.reconcile_interval_sec

    def mark_reconciled(self) -> None:
        self._last_reconcile = monotonic()

    @staticmethod
    def _elapsed(last_value: float | None) -> float:
        if last_value is None:
            return float("inf")
        return monotonic() - last_value
