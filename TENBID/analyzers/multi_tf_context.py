"""
Multi-Timeframe Context Aggregator

Central hub for aggregating and analyzing market data across multiple timeframes.
Provides hierarchical market view from D1 down to 5m.

Key Features:
- Aggregates data from 3+ timeframes (e.g., 1h, 15m, 5m)
- Calculates cross-TF trend alignment
- Detects TF conflicts (e.g., bullish on 5m, bearish on 1h)
- Provides weighted confidence based on TF hierarchy
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

from core.data_lineage import LineageTracker, DataSource, DataQuality, DataLineage

logger = logging.getLogger(__name__)


@dataclass
class TFAnalysis:
    """Analysis result for a single timeframe."""
    timeframe: str
    trend: int  # 1=bullish, -1=bearish, 0=neutral
    trend_strength: float  # 0.0 - 1.0
    support: float
    resistance: float
    volume_score: float  # 0.0 - 1.0
    atr: float
    signal_confidence: float  # 0.0 - 1.0
    lineage: Optional[DataLineage] = None


@dataclass
class MultiTFContext:
    """Aggregated multi-timeframe context."""
    symbol: str
    timestamp: datetime
    timeframes: List[str]  # Ordered from highest to lowest
    
    # Per-TF analysis
    tf_analysis: Dict[str, TFAnalysis]
    
    # Cross-TF metrics
    trend_alignment: float  # -1.0 (all bearish) to +1.0 (all bullish)
    trend_conflicts: List[str]  # List of conflicting TF pairs
    dominant_trend: str  # 'BULLISH', 'BEARISH', 'NEUTRAL', 'MIXED'
    
    # Key levels from higher TFs
    major_support: float
    major_resistance: float
    
    # Composite confidence
    composite_confidence: float  # Overall confidence in the context
    
    # Lineage tracking
    lineage: Optional[DataLineage] = None


class MultiTFContextAggregator:
    """
    Aggregates analysis from multiple timeframes into unified context.
    
    Usage:
        aggregator = MultiTFContextAggregator(config)
        context = aggregator.aggregate(tf_analysis_dict)
    """
    
    def __init__(self, config):
        """
        Initialize aggregator.
        
        Args:
            config: Configuration with timeframe weights and hierarchy
        """
        self.config = config
        
        # Timeframe hierarchy (highest to lowest importance)
        self.tf_hierarchy = config.get_list('MULTITF', 'timeframe_hierarchy', 
                                            fallback=['1h', '15m', '5m'])
        
        # Weights for each TF (higher TF = more weight for trend direction)
        self.tf_weights = {
            '1h': 0.5,
            '30m': 0.3,
            '15m': 0.15,
            '5m': 0.05
        }
        # Override with config if provided
        for tf in self.tf_hierarchy:
            weight_key = f'tf_weight_{tf}'
            if config.has_option('MULTITF', weight_key):
                self.tf_weights[tf] = config.getfloat('MULTITF', weight_key)
        
        # Normalize weights
        total_weight = sum(self.tf_weights.get(tf, 0.1) for tf in self.tf_hierarchy)
        self.tf_weights = {tf: w/total_weight for tf, w in self.tf_weights.items()}
        
        logger.info(f"MultiTFContextAggregator initialized with hierarchy: {self.tf_hierarchy}")
    
    def aggregate(self, tf_analysis: Dict[str, dict], symbol: str) -> MultiTFContext:
        """
        Aggregate individual TF analyses into unified context.
        
        Args:
            tf_analysis: Dict {timeframe: analysis_dict} from analyzers
            symbol: Trading symbol
            
        Returns:
            MultiTFContext with aggregated metrics
        """
        timestamp = datetime.now()
        
        # Convert raw analysis to TFAnalysis objects
        parsed_analysis = {}
        lineages = []
        
        for tf, analysis in tf_analysis.items():
            if not analysis or 'error' in analysis:
                logger.warning(f"No valid analysis for {tf}: {analysis.get('error', 'Unknown error')}")
                continue
            
            tf_analysis_obj = TFAnalysis(
                timeframe=tf,
                trend=analysis.get('trend', 0),
                trend_strength=analysis.get('trend_strength', 0.0),
                support=analysis.get('support', 0.0),
                resistance=analysis.get('resistance', 0.0),
                volume_score=analysis.get('volume_score', 0.0),
                atr=analysis.get('atr', 0.0),
                signal_confidence=analysis.get('confidence', 0.0),
                lineage=analysis.get('lineage')
            )
            parsed_analysis[tf] = tf_analysis_obj
            
            if tf_analysis_obj.lineage:
                lineages.append(tf_analysis_obj.lineage)
        
        # Calculate cross-TF metrics
        trend_alignment = self._calculate_trend_alignment(parsed_analysis)
        trend_conflicts = self._detect_conflicts(parsed_analysis)
        dominant_trend = self._determine_dominant_trend(parsed_analysis)
        
        # Get major levels from highest TF
        major_support, major_resistance = self._get_major_levels(parsed_analysis)
        
        # Calculate composite confidence
        composite_confidence = self._calculate_composite_confidence(
            parsed_analysis, trend_alignment, len(trend_conflicts)
        )
        
        # Create merged lineage
        merged_lineage = None
        if lineages:
            merged_lineage = LineageTracker.merge_lineages(
                lineages,
                method="multi_tf_aggregation",
                metadata={
                    'timeframes': list(parsed_analysis.keys()),
                    'trend_alignment': trend_alignment,
                    'dominant_trend': dominant_trend
                }
            )
        
        return MultiTFContext(
            symbol=symbol,
            timestamp=timestamp,
            timeframes=list(parsed_analysis.keys()),
            tf_analysis=parsed_analysis,
            trend_alignment=trend_alignment,
            trend_conflicts=trend_conflicts,
            dominant_trend=dominant_trend,
            major_support=major_support,
            major_resistance=major_resistance,
            composite_confidence=composite_confidence,
            lineage=merged_lineage
        )
    
    def _calculate_trend_alignment(self, tf_analysis: Dict[str, TFAnalysis]) -> float:
        """
        Calculate how aligned trends are across timeframes.
        
        Returns:
            float: -1.0 (all bearish) to +1.0 (all bullish), 0 = mixed
        """
        if not tf_analysis:
            return 0.0
        
        weighted_sum = 0.0
        total_weight = 0.0
        
        for tf, analysis in tf_analysis.items():
            weight = self.tf_weights.get(tf, 0.1)
            weighted_sum += analysis.trend * weight
            total_weight += weight
        
        if total_weight == 0:
            return 0.0
        
        return weighted_sum / total_weight
    
    def _detect_conflicts(self, tf_analysis: Dict[str, TFAnalysis]) -> List[str]:
        """
        Detect conflicts between adjacent timeframes.
        
        Returns:
            List of conflict descriptions (e.g., "1h bearish vs 15m bullish")
        """
        conflicts = []
        sorted_tfs = sorted(
            tf_analysis.keys(),
            key=lambda x: self.tf_hierarchy.index(x) if x in self.tf_hierarchy else 999
        )
        
        for i in range(len(sorted_tfs) - 1):
            higher_tf = sorted_tfs[i]
            lower_tf = sorted_tfs[i + 1]
            
            higher_trend = tf_analysis[higher_tf].trend
            lower_trend = tf_analysis[lower_tf].trend
            
            if higher_trend != 0 and lower_trend != 0 and higher_trend != lower_trend:
                higher_dir = "bullish" if higher_trend > 0 else "bearish"
                lower_dir = "bullish" if lower_trend > 0 else "bearish"
                conflicts.append(f"{higher_tf} {higher_dir} vs {lower_tf} {lower_dir}")
        
        return conflicts
    
    def _determine_dominant_trend(self, tf_analysis: Dict[str, TFAnalysis]) -> str:
        """
        Determine the dominant trend considering TF hierarchy.
        """
        if not tf_analysis:
            return "UNKNOWN"
        
        alignment = self._calculate_trend_alignment(tf_analysis)
        
        if abs(alignment) < 0.3:
            return "MIXED"
        elif alignment >= 0.3:
            return "BULLISH"
        else:
            return "BEARISH"
    
    def _get_major_levels(self, tf_analysis: Dict[str, TFAnalysis]) -> Tuple[float, float]:
        """
        Get major support/resistance from highest available TF.
        """
        if not tf_analysis:
            return 0.0, 0.0
        
        # Find highest TF with valid data
        for tf in self.tf_hierarchy:
            if tf in tf_analysis:
                analysis = tf_analysis[tf]
                if analysis.support > 0 and analysis.resistance > 0:
                    return analysis.support, analysis.resistance
        
        # Fallback to any available TF
        for tf, analysis in tf_analysis.items():
            if analysis.support > 0 and analysis.resistance > 0:
                return analysis.support, analysis.resistance
        
        return 0.0, 0.0
    
    def _calculate_composite_confidence(
        self,
        tf_analysis: Dict[str, TFAnalysis],
        trend_alignment: float,
        conflict_count: int
    ) -> float:
        """
        Calculate overall confidence in the multi-TF context.
        
        Higher confidence when:
        - Trends are aligned across TFs
        - Higher TFs have strong signals
        - Few conflicts
        """
        if not tf_analysis:
            return 0.0
        
        # Base confidence from individual TF confidences (weighted)
        base_confidence = 0.0
        total_weight = 0.0
        
        for tf, analysis in tf_analysis.items():
            weight = self.tf_weights.get(tf, 0.1)
            base_confidence += analysis.signal_confidence * weight
            total_weight += weight
        
        if total_weight > 0:
            base_confidence /= total_weight
        else:
            base_confidence = 0.0
        
        # Alignment bonus (up to +0.3)
        alignment_bonus = abs(trend_alignment) * 0.3
        
        # Conflict penalty (up to -0.2 per conflict)
        conflict_penalty = min(0.4, conflict_count * 0.2)
        
        # Higher TF strength bonus
        higher_tf_strength = 0.0
        for tf in ['1h', '30m']:
            if tf in tf_analysis:
                higher_tf_strength = max(higher_tf_strength, tf_analysis[tf].trend_strength * 0.2)
        
        composite = base_confidence + alignment_bonus + higher_tf_strength - conflict_penalty
        return max(0.0, min(1.0, composite))
    
    def get_context_summary(self, context: MultiTFContext) -> str:
        """
        Generate human-readable summary of multi-TF context.
        """
        lines = [
            f"Multi-TF Context for {context.symbol} @ {context.timestamp}",
            f"Dominant Trend: {context.dominant_trend}",
            f"Trend Alignment: {context.trend_alignment:.2f}",
            f"Composite Confidence: {context.composite_confidence:.2f}",
            "",
            "Timeframe Analysis:"
        ]
        
        for tf in context.timeframes:
            analysis = context.tf_analysis.get(tf)
            if analysis:
                trend_dir = "→" if analysis.trend == 0 else ("↑" if analysis.trend > 0 else "↓")
                lines.append(
                    f"  {tf}: {trend_dir} (strength={analysis.trend_strength:.2f}, "
                    f"conf={analysis.signal_confidence:.2f}) "
                    f"S:{analysis.support:.2f} R:{analysis.resistance:.2f}"
                )
        
        if context.trend_conflicts:
            lines.append("")
            lines.append("Conflicts Detected:")
            for conflict in context.trend_conflicts:
                lines.append(f"  ⚠️  {conflict}")
        
        lines.append("")
        lines.append(f"Major Levels: Support={context.major_support:.2f}, Resistance={context.major_resistance:.2f}")
        
        return "\n".join(lines)


# Helper function for use in other modules
def create_multi_tf_context(config, tf_analysis: Dict[str, dict], symbol: str) -> MultiTFContext:
    """
    Convenience function to create multi-TF context.
    
    Args:
        config: Application config
        tf_analysis: Dict of per-TF analysis results
        symbol: Trading symbol
        
    Returns:
        MultiTFContext object
    """
    aggregator = MultiTFContextAggregator(config)
    return aggregator.aggregate(tf_analysis, symbol)
