"""Exchange executor skeleton.

Executes approved TradePlan through BinanceFuturesConnector and records planned vs actual fills/costs.
"""

class ExchangeExecutor:
    async def execute(self, trade_plan: object) -> object:
        raise NotImplementedError

