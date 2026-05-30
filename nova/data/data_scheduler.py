"""Data access policy scheduler.

Controls REST/WS usage, orderbook TTL and intrabar replay budgets.
"""

class DataScheduler:
    def should_fetch_orderbook(self) -> bool:
        raise NotImplementedError

