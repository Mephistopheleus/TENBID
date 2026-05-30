"""Decision engine skeleton.

Combines matrix output, state, dynamics, costs and risk gates into a TradePlan.
"""

class DecisionEngine:
    def create_trade_plan(self) -> object:
        raise NotImplementedError("Create HOLD/OPEN/SHADOW_ONLY TradePlan")

