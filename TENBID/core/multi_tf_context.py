"""
Multi-Timeframe Context Engine v2.0
Центральный дирижёр таймфреймов для TENBID.

АРХИТЕКТУРА:
- Не дублирует логику в каждом анализаторе
- Синхронизирует временные фреймы, даёт базовые веса
- Модули могут корректировать локально, но база едина
- Настраиваемые влияния между ТФ (не жёсткие)
- Загрузка старших ТФ для разогрева с корреляцией к текущим данным

СИСТЕМА ВЕСОВ:
- Каждый ТФ имеет влияние на остальные (настраиваемое)
- Автотюнер крутит эти веса на основе результатов
- Матрица получает уже взвешенные векторы от всех ТФ
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class TFImportance(Enum):
    """Уровни важности таймфреймов."""
    CRITICAL = 1.0
    HIGH = 0.8
    MEDIUM = 0.6
    LOW = 0.4
    WARMUP = 0.2


@dataclass
class TFWeightConfig:
    """Конфигурация весов для одного таймфрейма."""
    timeframe: str
    base_weight: float
    influence_on_higher: float
    influence_on_lower: float
    decay_factor: float = 0.9
    confidence_threshold: float = 0.5


@dataclass
class TFAnalysisResult:
    """Результат анализа по одному таймфрейму."""
    timeframe: str
    timestamp: float
    trend_direction: int
    trend_strength: float
    support_levels: List[float]
    resistance_levels: List[float]
    volume_profile: Dict[str, Any]
    volatility: float
    signal_confidence: float
    analyzer_id: str
    lineage_id: Optional[str] = None


@dataclass
class CrossTFConflict:
    """Конфликт между таймфреймами."""
    tf1: str
    tf2: str
    conflict_type: str
    severity: float
    description: str


@dataclass
class MultiTFContextOutput:
    """Итоговый контекст для передачи в Матрицу."""
    symbol: str
    timestamp: float
    primary_tf: str
    weighted_trend_score: float
    trend_alignment: float
    major_support: float
    major_resistance: float
    key_levels: List[Dict[str, Any]]
    conflicts: List[CrossTFConflict]
    conflict_penalty: float
    volatility_profile: Dict[str, float]
    composite_confidence: float
    timeframes_analyzed: List[str]
    lineage_id: Optional[str] = None


class MultiTFContextEngine:
    """Центральный движок мульти-таймфрейм контекста."""
    
    def __init__(self, config: Optional[Dict] = None):
        self.tf_configs: Dict[str, TFWeightConfig] = {
            '5m': TFWeightConfig('5m', 1.0, 0.3, 0.0),
            '15m': TFWeightConfig('15m', 0.8, 0.5, 0.4),
            '30m': TFWeightConfig('30m', 0.7, 0.6, 0.5),
            '1h': TFWeightConfig('1h', 0.6, 0.7, 0.6),
            '2h': TFWeightConfig('2h', 0.5, 0.6, 0.5),
            '4h': TFWeightConfig('4h', 0.4, 0.5, 0.4),
            'D1': TFWeightConfig('D1', 0.3, 0.3, 0.3),
        }
        
        if config:
            self._load_config(config)
        
        self.latest_analyses: Dict[str, TFAnalysisResult] = {}
        self.analysis_history: List[TFAnalysisResult] = []
        self.max_history_length = 100
        self.cross_tf_weights = self._calculate_cross_tf_weights()
        
        logger.info(f"MultiTFContextEngine initialized with {len(self.tf_configs)} timeframes")
    
    def _load_config(self, config: Dict):
        if 'tf_weights' in config:
            for tf, weight_data in config['tf_weights'].items():
                if tf in self.tf_configs:
                    cfg = self.tf_configs[tf]
                    cfg.base_weight = weight_data.get('base', cfg.base_weight)
                    cfg.influence_on_higher = weight_data.get('inf_higher', cfg.influence_on_higher)
                    cfg.influence_on_lower = weight_data.get('inf_lower', cfg.influence_on_lower)
    
    def _calculate_cross_tf_weights(self) -> Dict[Tuple[str, str], float]:
        weights = {}
        tf_list = list(self.tf_configs.keys())
        
        for tf1 in tf_list:
            for tf2 in tf_list:
                if tf1 == tf2:
                    weights[(tf1, tf2)] = 1.0
                    continue
                
                cfg1 = self.tf_configs[tf1]
                idx1, idx2 = tf_list.index(tf1), tf_list.index(tf2)
                
                if idx1 < idx2:
                    weight = cfg1.influence_on_lower * self.tf_configs[tf2].base_weight
                else:
                    weight = cfg1.influence_on_higher * self.tf_configs[tf2].base_weight
                
                weights[(tf1, tf2)] = weight
        
        return weights
    
    def update_weights(self, new_weights: Dict[str, Dict]):
        for tf, params in new_weights.items():
            if tf in self.tf_configs:
                cfg = self.tf_configs[tf]
                if 'base_weight' in params:
                    cfg.base_weight = params['base_weight']
                if 'influence_on_higher' in params:
                    cfg.influence_on_higher = params['influence_on_higher']
                if 'influence_on_lower' in params:
                    cfg.influence_on_lower = params['influence_on_lower']
        
        self.cross_tf_weights = self._calculate_cross_tf_weights()
        logger.info("MultiTF weights updated by Autotuner")
    
    def add_analysis(self, result: TFAnalysisResult):
        self.latest_analyses[result.timeframe] = result
        self.analysis_history.append(result)
        
        if len(self.analysis_history) > self.max_history_length:
            self.analysis_history = self.analysis_history[-self.max_history_length:]
        
        logger.debug(f"Added analysis for {result.timeframe}: trend={result.trend_direction}, conf={result.signal_confidence}")
    
    def get_context(self, symbol: str, primary_tf: str = '5m') -> Optional[MultiTFContextOutput]:
        if not self.latest_analyses:
            logger.warning("No analyses available for context generation")
            return None
        
        active_tfs = [
            tf for tf, result in self.latest_analyses.items()
            if result.signal_confidence >= self.tf_configs.get(tf, TFWeightConfig(tf, 0.5, 0, 0)).confidence_threshold
        ]
        
        if len(active_tfs) < 1:
            logger.warning("No active TFs with sufficient confidence")
            return None
        
        weighted_trend_score = 0.0
        total_weight = 0.0
        
        for tf in active_tfs:
            result = self.latest_analyses[tf]
            weight = self.tf_configs.get(tf, TFWeightConfig(tf, 0.5, 0, 0)).base_weight
            cross_weight = self._get_cross_tf_influence(tf, active_tfs)
            effective_weight = weight * cross_weight
            
            weighted_trend_score += result.trend_direction * result.signal_confidence * effective_weight
            total_weight += effective_weight
        
        if total_weight > 0:
            weighted_trend_score /= total_weight
        
        trend_alignment = self._calculate_trend_alignment(active_tfs)
        major_support, major_resistance, key_levels = self._aggregate_key_levels(active_tfs)
        conflicts = self._detect_conflicts(active_tfs)
        conflict_penalty = sum(c.severity for c in conflicts) * 0.1
        
        volatility_profile = {tf: result.volatility for tf, result in self.latest_analyses.items() if tf in active_tfs}
        
        base_confidence = np.mean([self.latest_analyses[tf].signal_confidence for tf in active_tfs])
        composite_confidence = max(0.0, base_confidence - conflict_penalty)
        
        output = MultiTFContextOutput(
            symbol=symbol,
            timestamp=datetime.now().timestamp(),
            primary_tf=primary_tf,
            weighted_trend_score=weighted_trend_score,
            trend_alignment=trend_alignment,
            major_support=major_support,
            major_resistance=major_resistance,
            key_levels=key_levels,
            conflicts=conflicts,
            conflict_penalty=conflict_penalty,
            volatility_profile=volatility_profile,
            composite_confidence=composite_confidence,
            timeframes_analyzed=active_tfs
        )
        
        logger.info(f"MultiTF context for {symbol}: trend={weighted_trend_score:.2f}, alignment={trend_alignment:.2f}, conf={composite_confidence:.2f}")
        return output
    
    def _get_cross_tf_influence(self, target_tf: str, active_tfs: List[str]) -> float:
        total_influence = 0.0
        for other_tf in active_tfs:
            if other_tf == target_tf:
                continue
            influence = self.cross_tf_weights.get((other_tf, target_tf), 0.1)
            total_influence += influence
        return 1.0 + (total_influence / len(active_tfs)) if active_tfs else 1.0
    
    def _calculate_trend_alignment(self, active_tfs: List[str]) -> float:
        if len(active_tfs) < 2:
            return 1.0
        
        directions = [self.latest_analyses[tf].trend_direction for tf in active_tfs]
        majority_direction = max(set(directions), key=directions.count)
        agreement_count = directions.count(majority_direction)
        
        return agreement_count / len(active_tfs)
    
    def _aggregate_key_levels(self, active_tfs: List[str]) -> Tuple[float, float, List[Dict]]:
        all_supports = []
        all_resistances = []
        key_levels = []
        
        for tf in active_tfs:
            result = self.latest_analyses[tf]
            weight = self.tf_configs.get(tf, TFWeightConfig(tf, 0.5, 0, 0)).base_weight
            
            for s in result.support_levels:
                all_supports.append((s, weight, tf))
            for r in result.resistance_levels:
                all_resistances.append((r, weight, tf))
        
        clustered_supports = self._cluster_levels(all_supports, tolerance_pct=0.005)
        clustered_resistances = self._cluster_levels(all_resistances, tolerance_pct=0.005)
        
        major_support = clustered_supports[0][0] if clustered_supports else 0.0
        major_resistance = clustered_resistances[-1][0] if clustered_resistances else 0.0
        
        for level, strength, tf in clustered_supports[:3]:
            key_levels.append({'type': 'support', 'price': level, 'strength': strength, 'timeframe': tf})
        for level, strength, tf in clustered_resistances[:3]:
            key_levels.append({'type': 'resistance', 'price': level, 'strength': strength, 'timeframe': tf})
        
        return major_support, major_resistance, key_levels
    
    def _cluster_levels(self, levels: List[Tuple[float, float, str]], tolerance_pct: float = 0.005) -> List[Tuple[float, float, str]]:
        if not levels:
            return []
        
        sorted_levels = sorted(levels, key=lambda x: x[0])
        clusters = []
        current_cluster = [sorted_levels[0]]
        
        for i in range(1, len(sorted_levels)):
            prev_price = current_cluster[-1][0]
            curr_price = sorted_levels[i][0]
            
            if abs(curr_price - prev_price) / prev_price <= tolerance_pct:
                current_cluster.append(sorted_levels[i])
            else:
                avg_price = sum(l[0] for l in current_cluster) / len(current_cluster)
                total_strength = sum(l[1] for l in current_cluster)
                dominant_tf = max(set(l[2] for l in current_cluster), key=[l[2] for l in current_cluster].count)
                clusters.append((avg_price, total_strength, dominant_tf))
                current_cluster = [sorted_levels[i]]
        
        if current_cluster:
            avg_price = sum(l[0] for l in current_cluster) / len(current_cluster)
            total_strength = sum(l[1] for l in current_cluster)
            dominant_tf = max(set(l[2] for l in current_cluster), key=[l[2] for l in current_cluster].count)
            clusters.append((avg_price, total_strength, dominant_tf))
        
        return clusters
    
    def _detect_conflicts(self, active_tfs: List[str]) -> List[CrossTFConflict]:
        conflicts = []
        
        for i, tf1 in enumerate(active_tfs):
            for tf2 in active_tfs[i+1:]:
                result1 = self.latest_analyses[tf1]
                result2 = self.latest_analyses[tf2]
                
                if result1.trend_direction != 0 and result2.trend_direction != 0:
                    if result1.trend_direction != result2.trend_direction:
                        severity = min(result1.signal_confidence, result2.signal_confidence)
                        conflicts.append(CrossTFConflict(
                            tf1=tf1,
                            tf2=tf2,
                            conflict_type='trend_opposite',
                            severity=severity,
                            description=f"{tf1} {'bullish' if result1.trend_direction > 0 else 'bearish'} vs {tf2} {'bullish' if result2.trend_direction > 0 else 'bearish'}"
                        ))
        
        return conflicts
    
    def get_statistics(self) -> Dict:
        return {
            'timeframes_configured': len(self.tf_configs),
            'active_analyses': len(self.latest_analyses),
            'history_size': len(self.analysis_history),
            'tf_configs': {
                tf: {'base_weight': cfg.base_weight, 'inf_higher': cfg.influence_on_higher, 'inf_lower': cfg.influence_on_lower}
                for tf, cfg in self.tf_configs.items()
            }
        }


multi_tf_engine = MultiTFContextEngine()
