"""
Volume Profile Analyzer - Volume-based Support/Resistance Detection.
Multi-Timeframe Support Enabled.

Analyzes volume distribution across price levels to identify:
- POC (Point of Control) - price with highest volume
- Value Area (VA) - range containing 70% of volume
- High/Low Volume Nodes - support/resistance zones

Supports analysis across multiple timeframes simultaneously.
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np
import pandas as pd
from core.data_lineage import AnalysisContext, LineageTracker, DataSource, DataQuality
from analyzers.multi_tf_context import MultiTFContextAggregator

logger = logging.getLogger(__name__)

@dataclass
class VolumeProfileResult:
    """Volume profile analysis result."""
    poc: float  # Point of Control price
    value_area_high: float
    value_area_low: float
    value_area_width: float
    current_price_vs_poc: float  # % distance from POC
    volume_distribution: str  # 'BALANCED', 'SKEWED_UP', 'SKEWED_DOWN'
    support_levels: List[float]
    resistance_levels: List[float]
    confidence: float
    timeframe: Optional[str] = None


class VolumeProfileAnalyzer:
    def __init__(self, config=None, lookback_bars: int = 100, value_area_percent: float = 0.70):
        """
        Initialize Volume Profile Analyzer with multi-TF support.
        
        Args:
            config: Application configuration
            lookback_bars: Number of bars to analyze
            value_area_percent: Percentage of volume in value area (default 70%)
        """
        self.config = config
        self.lookback_bars = lookback_bars
        self.value_area_percent = value_area_percent
        
        # Minimum bins for profile
        self.NUM_PRICE_BINS = 50
        
        # Timeframes for analysis
        self.timeframes = ['1h', '15m', '5m']
        if config and hasattr(config, 'get_list'):
            self.timeframes = config.get_list('MULTITF', 'timeframe_hierarchy', 
                                              fallback=['1h', '15m', '5m'])
        
        # Aggregator for multi-TF results
        self.aggregator = MultiTFContextAggregator(config) if config else MultiTFContextAggregator()
        
        logger.info(f"VolumeProfileAnalyzer initialized (lookback={lookback_bars}, VA={value_area_percent*100}%, multi_tf=True)")
    
    def analyze(self, context: AnalysisContext, symbol: str = None) -> Dict:
        """
        Analyze volume profile across all available timeframes.
        
        Args:
            context: AnalysisContext with market data
            symbol: Trading symbol
            
        Returns:
            Dict with aggregated results and multi-TF context
        """
        try:
            # Collect data from all available timeframes
            tf_data = self._collect_all_timeframe_data(context, symbol)
            
            if not tf_data:
                lineage = LineageTracker.create_calculated(
                    method="volume_profile_no_data",
                    dependencies=[context.data_lineage] if context.data_lineage else [],
                    quality=DataQuality.VERY_LOW,
                    metadata={'error': 'No data available on any timeframe'}
                )
                return {
                    "error": "No data available",
                    "confidence": 0.0,
                    "lineage": lineage
                }
            
            # Analyze each timeframe separately
            per_timeframe_results = {}
            lineages = []
            
            for tf, (df, current_price, lineage) in tf_data.items():
                result = self._analyze_single_timeframe(df, current_price, tf, lineage)
                if result and 'error' not in result:
                    per_timeframe_results[tf] = result
                    if result.get('lineage'):
                        lineages.append(result['lineage'])
            
            if not per_timeframe_results:
                lineage = LineageTracker.create_calculated(
                    method="volume_profile_analysis_failed",
                    dependencies=[context.data_lineage] if context.data_lineage else [],
                    quality=DataQuality.LOW,
                    metadata={'error': 'Analysis failed on all timeframes'}
                )
                return {
                    "error": "Analysis failed",
                    "confidence": 0.0,
                    "lineage": lineage
                }
            
            # Aggregate results using MultiTFContextAggregator
            # Convert to format expected by aggregator
            tf_analysis_for_aggregator = {}
            for tf, result in per_timeframe_results.items():
                # Determine trend from volume distribution
                trend = 1 if result.get('volume_distribution') == 'SKEWED_UP' else \
                       (-1 if result.get('volume_distribution') == 'SKEWED_DOWN' else 0)
                
                tf_analysis_for_aggregator[tf] = {
                    'trend': trend,
                    'trend_strength': abs(result.get('current_price_vs_poc', 0)) / 100,
                    'support': result.get('support_levels', [0])[0] if result.get('support_levels') else 0,
                    'resistance': result.get('resistance_levels', [0])[0] if result.get('resistance_levels') else 0,
                    'volume_score': result.get('confidence', 0),
                    'atr': 0,
                    'confidence': result.get('confidence', 0)
                }
            
            multi_tf_context = self.aggregator.aggregate(tf_analysis_for_aggregator, symbol or "UNKNOWN")
            
            # Build final result
            final_result = {
                "timeframes_analyzed": list(per_timeframe_results.keys()),
                "per_timeframe_results": per_timeframe_results,
                "multi_tf_context": {
                    "dominant_trend": multi_tf_context.dominant_trend,
                    "trend_alignment": multi_tf_context.trend_alignment,
                    "composite_confidence": multi_tf_context.composite_confidence,
                    "trend_conflicts": multi_tf_context.trend_conflicts
                },
                "aggregate_poc": np.mean([r['poc'] for r in per_timeframe_results.values()]),
                "aggregate_value_area": {
                    "high": np.mean([r['value_area_high'] for r in per_timeframe_results.values()]),
                    "low": np.mean([r['value_area_low'] for r in per_timeframe_results.values()])
                },
                "dominant_distribution": self._get_dominant_distribution(per_timeframe_results),
                "confidence": multi_tf_context.composite_confidence,
                "lineage": multi_tf_context.lineage
            }
            
            context.add_result("VolumeProfile", final_result, multi_tf_context.lineage)
            return final_result
            
        except Exception as e:
            lineage = LineageTracker.create_calculated(
                method="volume_profile_error",
                dependencies=[context.data_lineage] if context.data_lineage else [],
                quality=DataQuality.VERY_LOW,
                metadata={'error': str(e)}
            )
            return {
                "error": str(e),
                "confidence": 0.0,
                "lineage": lineage
            }
    
    def _collect_all_timeframe_data(self, context: AnalysisContext, symbol: str) -> Dict[str, Tuple]:
        """
        Collect data from all available timeframes (base + synthetic).
        Returns: dict {timeframe: (df, current_price, lineage)}
        """
        tf_data = {}
        
        # Check base market data
        base_df = context.get_data(DataSource.MARKET_DATA, symbol=symbol)
        if base_df is not None and not base_df.empty:
            current_price = base_df['close'].iloc[-1]
            tf_data[context.timeframe] = (base_df, current_price, context.data_lineage)
        
        # Check synthetic timeframes
        for tf in self.timeframes:
            synthetic_df = context.get_data(DataSource.SYNTHETIC_TF, timeframe=tf)
            if synthetic_df is not None and not synthetic_df.empty:
                synthetic_lineage = LineageTracker.create_calculated(
                    method=f"synthetic_{tf}",
                    dependencies=[context.data_lineage] if context.data_lineage else [],
                    quality=DataQuality.MEDIUM,
                    metadata={'timeframe': tf, 'source': 'synthetic'}
                )
                current_price = synthetic_df['close'].iloc[-1]
                tf_data[tf] = (synthetic_df, current_price, synthetic_lineage)
        
        return tf_data
    
    def _analyze_single_timeframe(self, df: pd.DataFrame, current_price: float, 
                                   timeframe: str, lineage) -> Dict:
        """Analyze volume profile on a single timeframe."""
        if len(df) < 10:
            return {"error": "Insufficient data", "confidence": 0.0, "timeframe": timeframe}
        
        result = self.analyze_legacy(df, current_price)
        result.timeframe = timeframe
        result.lineage = lineage
        
        return {
            "poc": result.poc,
            "value_area_high": result.value_area_high,
            "value_area_low": result.value_area_low,
            "value_area_width": result.value_area_width,
            "current_price_vs_poc": result.current_price_vs_poc,
            "volume_distribution": result.volume_distribution,
            "support_levels": result.support_levels,
            "resistance_levels": result.resistance_levels,
            "confidence": result.confidence,
            "timeframe": timeframe,
            "lineage": lineage
        }
    
    def _get_dominant_distribution(self, per_timeframe_results: Dict) -> str:
        """Get the most common volume distribution across timeframes."""
        distributions = [r['volume_distribution'] for r in per_timeframe_results.values()]
        if not distributions:
            return 'UNKNOWN'
        
        # Count occurrences
        counts = {}
        for d in distributions:
            counts[d] = counts.get(d, 0) + 1
        
        return max(counts, key=counts.get)
    
    def analyze_legacy(self, df: pd.DataFrame, current_price: float) -> VolumeProfileResult:
        """
        Analyze volume profile from OHLCV data. (Legacy method for single-TF analysis)
        
        Args:
            df: DataFrame with columns ['high', 'low', 'close', 'volume']
            current_price: Current market price
            
        Returns:
            VolumeProfileResult with POC, value area, and levels
        """
        if len(df) < 10:
            return self._empty_result(current_price)
        
        # Get recent data
        df_recent = df.tail(self.lookback_bars).copy()
        
        if len(df_recent) < 10:
            return self._empty_result(current_price)
        
        # Calculate price range
        price_min = df_recent['low'].min()
        price_max = df_recent['high'].max()
        
        if price_max <= price_min:
            return self._empty_result(current_price)
        
        # Create price bins for volume distribution
        bin_edges = np.linspace(price_min, price_max, self.NUM_PRICE_BINS + 1)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        
        # Distribute volume across bins
        volume_by_bin = self._distribute_volume(df_recent, bin_edges)
        
        if volume_by_bin.sum() == 0:
            return self._empty_result(current_price)
        
        # Find POC (Point of Control)
        poc_idx = np.argmax(volume_by_bin)
        poc = bin_centers[poc_idx]
        
        # Calculate Value Area (70% of volume around POC)
        va_high, va_low = self._calculate_value_area(
            bin_centers, volume_by_bin, poc, self.value_area_percent
        )
        
        # Find high/low volume nodes
        support_levels, resistance_levels = self._find_volume_nodes(
            bin_centers, volume_by_bin, current_price
        )
        
        # Determine volume distribution shape
        distribution = self._classify_distribution(volume_by_bin, poc_idx)
        
        # Calculate distance from POC
        poc_distance_pct = (current_price - poc) / poc * 100
        
        # Calculate confidence based on profile clarity
        confidence = self._calculate_confidence(volume_by_bin, poc_idx)
        
        return VolumeProfileResult(
            poc=round(poc, 8),
            value_area_high=round(va_high, 8),
            value_area_low=round(va_low, 8),
            value_area_width=round(va_high - va_low, 8),
            current_price_vs_poc=round(poc_distance_pct, 4),
            volume_distribution=distribution,
            support_levels=[round(l, 8) for l in support_levels[:3]],
            resistance_levels=[round(r, 8) for r in resistance_levels[:3]],
            confidence=round(confidence, 4)
        )
    
    def _distribute_volume(self, df: pd.DataFrame, bin_edges: np.ndarray) -> np.ndarray:
        """
        Distribute trading volume across price bins.
        
        Uses bar's average price weighted by volume.
        """
        volume_dist = np.zeros(len(bin_edges) - 1)
        
        for _, row in df.iterrows():
            # Use typical price (HLC average)
            typical_price = (row['high'] + row['low'] + row['close']) / 3
            volume = row['volume']
            
            # Find which bin this price falls into
            bin_idx = np.searchsorted(bin_edges, typical_price) - 1
            bin_idx = max(0, min(len(volume_dist) - 1, bin_idx))
            
            volume_dist[bin_idx] += volume
        
        return volume_dist
    
    def _calculate_value_area(
        self,
        bin_centers: np.ndarray,
        volume_by_bin: np.ndarray,
        poc: float,
        target_percent: float
    ) -> Tuple[float, float]:
        """
        Calculate Value Area containing target_percent of total volume.
        
        Starts from POC and expands outward until target is reached.
        """
        total_volume = volume_by_bin.sum()
        target_volume = total_volume * target_percent
        
        # Find POC index
        poc_idx = np.argmin(np.abs(bin_centers - poc))
        
        # Expand from POC
        left_idx = poc_idx
        right_idx = poc_idx
        accumulated_volume = volume_by_bin[poc_idx]
        
        while accumulated_volume < target_volume:
            # Check which side to expand
            left_vol = volume_by_bin[left_idx - 1] if left_idx > 0 else 0
            right_vol = volume_by_bin[right_idx + 1] if right_idx < len(volume_by_bin) - 1 else 0
            
            if left_vol >= right_vol and left_idx > 0:
                left_idx -= 1
                accumulated_volume += volume_by_bin[left_idx]
            elif right_idx < len(volume_by_bin) - 1:
                right_idx += 1
                accumulated_volume += volume_by_bin[right_idx]
            else:
                break
        
        va_low = bin_centers[left_idx]
        va_high = bin_centers[right_idx]
        
        return va_high, va_low
    
    def _find_volume_nodes(
        self,
        bin_centers: np.ndarray,
        volume_by_bin: np.ndarray,
        current_price: float
    ) -> Tuple[List[float], List[float]]:
        """
        Find high volume nodes (support/resistance) and low volume nodes.
        
        High volume = strong support/resistance
        Low volume = price moves through quickly
        """
        avg_volume = np.mean(volume_by_bin)
        high_vol_threshold = avg_volume * 1.5
        low_vol_threshold = avg_volume * 0.5
        
        support_levels = []
        resistance_levels = []
        
        for i, (price, vol) in enumerate(zip(bin_centers, volume_by_bin)):
            if vol >= high_vol_threshold:
                if price < current_price:
                    support_levels.append(price)
                elif price > current_price:
                    resistance_levels.append(price)
        
        # Sort by proximity to current price
        support_levels.sort(reverse=True)  # Closest first below
        resistance_levels.sort()  # Closest first above
        
        return support_levels, resistance_levels
    
    def _classify_distribution(self, volume_by_bin: np.ndarray, poc_idx: int) -> str:
        """
        Classify volume distribution shape.
        
        BALANCED: Symmetric around POC
        SKEWED_UP: More volume above POC (bullish)
        SKEWED_DOWN: More volume below POC (bearish)
        """
        if poc_idx <= 5 or poc_idx >= len(volume_by_bin) - 5:
            return 'EXTREME'  # POC at edge
        
        # Compare volume above and below POC
        volume_below = volume_by_bin[:poc_idx].sum()
        volume_above = volume_by_bin[poc_idx+1:].sum()
        
        if volume_below == 0 and volume_above == 0:
            return 'BALANCED'
        
        ratio = volume_above / max(volume_below, 1)
        
        if ratio > 1.3:
            return 'SKEWED_UP'
        elif ratio < 0.7:
            return 'SKEWED_DOWN'
        else:
            return 'BALANCED'
    
    def _calculate_confidence(self, volume_by_bin: np.ndarray, poc_idx: int) -> float:
        """
        Calculate confidence in the volume profile analysis.
        
        Higher confidence when:
        - Clear POC (one dominant bin)
        - Smooth distribution
        - Sufficient volume
        """
        total_volume = volume_by_bin.sum()
        poc_volume = volume_by_bin[poc_idx]
        
        # POC dominance (higher = clearer profile)
        poc_dominance = poc_volume / max(total_volume / len(volume_by_bin), 1)
        
        # Normalize to 0-1
        confidence = min(1.0, poc_dominance / 3.0)
        
        return confidence
    
    def _empty_result(self, current_price: float) -> VolumeProfileResult:
        """Return empty result when insufficient data."""
        return VolumeProfileResult(
            poc=current_price,
            value_area_high=current_price * 1.02,
            value_area_low=current_price * 0.98,
            value_area_width=current_price * 0.04,
            current_price_vs_poc=0.0,
            volume_distribution='UNKNOWN',
            support_levels=[],
            resistance_levels=[],
            confidence=0.0
        )
    
    def get_signal(self, profile: VolumeProfileResult, position: str = None) -> Tuple[float, float]:
        """
        Generate trading signal from volume profile.
        
        Returns:
            score: -1.0 to +1.0 (bearish to bullish)
            confidence: 0.0 to 1.0
        """
        if profile.confidence < 0.3:
            return 0.0, 0.0
        
        score = 0.0
        
        # Price relative to POC
        if profile.current_price_vs_poc > 2:  # Price well above POC
            # Might be overextended
            score -= 0.3
        elif profile.current_price_vs_poc < -2:  # Price well below POC
            # Potential bounce
            score += 0.3
        
        # Distribution skew
        if profile.volume_distribution == 'SKEWED_UP':
            score += 0.2
        elif profile.volume_distribution == 'SKEWED_DOWN':
            score -= 0.2
        
        # Position relative to value area
        # (would need current_price passed in)
        
        confidence = profile.confidence
        
        return score, confidence
