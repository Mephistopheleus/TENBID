"""Risk manager skeleton.

Uses RiskDynamics and SafetyKernel to accept, shrink or block candidates.
"""

class RiskManager:
    def evaluate(self) -> object:
        raise NotImplementedError

