"""Online shadow engine.

Creates ScenarioRequest from current HOLD or skipped candidates and delegates calculation to ScenarioEvaluator.
"""

class ShadowEngine:
    def on_trade_plan(self, trade_plan: object) -> None:
        raise NotImplementedError

