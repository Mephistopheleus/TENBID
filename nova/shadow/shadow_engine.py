"""Online shadow engine.

Creates ScenarioRequest from current HOLD, skipped candidates and forbidden
candidates, then delegates calculation to ScenarioEvaluator. Its key duty is to
learn whether a prohibition protected the system or was too strict under the
recorded context. It never executes the counterfactual plan.
"""

class ShadowEngine:
    def on_trade_plan(self, trade_plan: object) -> None:
        raise NotImplementedError
