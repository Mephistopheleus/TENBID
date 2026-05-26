"""
TENBID v2.0 - AutoTuner (Автотюнер)
Модуль автоматической настройки параметров системы.
Оптимизирует веса анализаторов, пороги уверенности, параметры исполнения.
Работает на данных Shadow Lab и History DB.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import logging
import random

logger = logging.getLogger(__name__)

@dataclass
class TuningParameter:
    name: str
    current_value: float
    min_value: float
    max_value: float
    step: float
    best_value: Optional[float] = None
    score: float = 0.0

@dataclass
class TuningResult:
    parameter_name: str
    original_value: float
    optimized_value: float
    improvement_percent: float
    confidence: float
    test_trades: int
    win_rate_before: float
    win_rate_after: float

class AutoTunerV2:
    def __init__(self):
        self.parameters: Dict[str, TuningParameter] = {}
        self.tuning_history: List[TuningResult] = []
        self.best_score = 0.0
        self.best_parameters: Dict[str, float] = {}
        self._initialize_default_parameters()
        logger.info("AutoTunerV2 инициализирован")
    
    def _initialize_default_parameters(self):
        self.parameters['weight_trend'] = TuningParameter(name='weight_trend', current_value=0.20, min_value=0.05, max_value=0.40, step=0.05)
        self.parameters['weight_volume'] = TuningParameter(name='weight_volume', current_value=0.20, min_value=0.05, max_value=0.40, step=0.05)
        self.parameters['weight_news'] = TuningParameter(name='weight_news', current_value=0.10, min_value=0.0, max_value=0.25, step=0.05)
        self.parameters['weight_orderbook'] = TuningParameter(name='weight_orderbook', current_value=0.15, min_value=0.05, max_value=0.30, step=0.05)
        self.parameters['min_confidence_entry'] = TuningParameter(name='min_confidence_entry', current_value=0.5, min_value=0.3, max_value=0.8, step=0.05)
        self.parameters['trailing_stop_percent'] = TuningParameter(name='trailing_stop_percent', current_value=0.3, min_value=0.1, max_value=1.0, step=0.1)
        self.parameters['max_drawdown_limit'] = TuningParameter(name='max_drawdown_limit', current_value=0.15, min_value=0.05, max_value=0.30, step=0.02)
        logger.info(f"Инициализировано {len(self.parameters)} параметров")
    
    def get_current_weights(self) -> Dict[str, float]:
        weights = {}
        weight_params = [k for k in self.parameters.keys() if k.startswith('weight_')]
        total = sum(self.parameters[k].current_value for k in weight_params)
        if total > 0:
            for key in weight_params:
                analyzer_type = key.replace('weight_', '')
                weights[analyzer_type] = self.parameters[key].current_value / total
        return weights
    
    def get_execution_params(self) -> Dict[str, float]:
        return {
            'trailing_stop_percent': self.parameters['trailing_stop_percent'].current_value,
            'min_confidence_entry': self.parameters['min_confidence_entry'].current_value,
        }
    
    def get_risk_params(self) -> Dict[str, float]:
        return {'max_drawdown_limit': self.parameters['max_drawdown_limit'].current_value}
    
    def evaluate_performance(self, trades: List[Dict]) -> float:
        if not trades: return 0.0
        winning = sum(1 for t in trades if t.get('pnl', 0) > 0)
        win_rate = winning / len(trades)
        total_pnl = sum(t.get('pnl', 0) for t in trades)
        avg_win = sum(t.get('pnl', 0) for t in trades if t.get('pnl', 0) > 0) / max(1, winning)
        avg_loss = abs(sum(t.get('pnl', 0) for t in trades if t.get('pnl', 0) <= 0) / max(1, len(trades) - winning))
        pf = avg_win / avg_loss if avg_loss > 0 else 0
        max_dd = max([0.0] + [-t.get('pnl', 0) for t in trades if t.get('pnl', 0) < 0])
        score = win_rate * 0.4 + min(1.0, pf / 2.0) * 0.3 + max(0.0, 1.0 - max_dd) * 0.3
        return min(1.0, score)
    
    def tune_parameter(self, param_name: str, historical_data: List[Dict], iterations: int = 10) -> TuningResult:
        if param_name not in self.parameters: return None
        param = self.parameters[param_name]
        original_value = param.current_value
        base_score = self.evaluate_performance(historical_data)
        best_value, best_score = original_value, base_score
        for i in range(iterations):
            direction = random.choice([-1, 1])
            step_size = param.step * (1.0 - i / iterations)
            new_value = max(param.min_value, min(param.max_value, param.current_value + direction * step_size))
            param.current_value = new_value
            test_trades = self._simulate_trading(historical_data, param_name, new_value)
            new_score = self.evaluate_performance(test_trades)
            if new_score > best_score: best_score, best_value = new_score, new_value
            param.current_value = original_value
        param.current_value = best_value
        param.best_value = best_value
        param.score = best_score
        improvement = ((best_score - base_score) / base_score * 100) if base_score > 0 else 0
        result = TuningResult(param_name, original_value, best_value, improvement, best_score, len(historical_data), base_score, best_score)
        self.tuning_history.append(result)
        logger.info(f"Настройка {param_name}: {original_value:.3f} -> {best_value:.3f}, улучшение={improvement:.1f}%")
        return result
    
    def _simulate_trading(self, data: List[Dict], param_name: str, param_value: float) -> List[Dict]:
        simulated = []
        for t in data:
            base_pnl = t.get('pnl', 0)
            if param_name.startswith('weight_'): pnl = base_pnl * (1.0 + (param_value - 0.15) * 0.5)
            elif param_name == 'trailing_stop_percent': pnl = base_pnl * (1.0 - param_value * 0.1) if base_pnl > 0 else base_pnl * (1.0 - param_value * 0.2)
            elif param_name == 'min_confidence_entry': pnl = base_pnl * (1.0 + (param_value - 0.5) * 0.3) if abs(base_pnl) > 0.01 else 0
            else: pnl = base_pnl
            new_t = t.copy()
            new_t['pnl'] = pnl
            simulated.append(new_t)
        return simulated
    
    def apply_optimized_parameters(self, matrix: Any, multi_tf_engine: Any, execution: Any, capital_controller: Any):
        logger.info("Применение оптимизированных параметров...")
        weights = self.get_current_weights()
        if hasattr(matrix, 'update_weights'): matrix.update_weights(weights)
        exec_params = self.get_execution_params()
        if hasattr(execution, 'min_profit_threshold'): execution.min_profit_threshold = exec_params['min_profit_threshold']
        if hasattr(execution, 'trailing_stop_percent'): execution.trailing_stop_percent = exec_params['trailing_stop_percent']
        risk_params = self.get_risk_params()
        if hasattr(capital_controller, 'limits'): capital_controller.limits.max_drawdown_percent = risk_params['max_drawdown_limit']
        logger.info("Параметры применены")
    
    def get_tuning_report(self) -> Dict:
        if not self.tuning_history: return {"status": "no_tuning_performed"}
        improvements = [r.improvement_percent for r in self.tuning_history if r.improvement_percent > 0]
        return {
            "status": "completed",
            "parameters_tuned": len(self.tuning_history),
            "total_improvement_percent": sum(improvements),
            "average_improvement_percent": sum(improvements) / len(improvements) if improvements else 0,
            "recent_results": [{"parameter": r.parameter_name, "from": r.original_value, "to": r.optimized_value, "improvement": r.improvement_percent} for r in self.tuning_history[-5:]]
        }
