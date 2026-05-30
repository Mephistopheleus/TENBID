"""
Derivatives Analyzer - Funding Rate and Open Interest Analysis.
Multi-Timeframe Support Enabled.

Analyzes futures market data:
- Funding Rate (cost of holding positions)
- Open Interest (total outstanding contracts)
- Long/Short Ratio
- Liquidation heatmaps

These metrics provide insight into market sentiment and potential squeeze scenarios.
Supports multi-timeframe analysis by analyzing trends across different time periods.
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from core.analysis_context import AnalysisContext
from core.data_lineage import DataLineageManager, LineageNode, LineageGraph, DataQuality, LineageTracker
from analyzers.multi_tf_context import MultiTFContextAggregator

logger = logging.getLogger(__name__)

@dataclass
class DerivativesMetrics:
    """Derivatives market metrics."""
    funding_rate: float  # Current funding rate (%)
    funding_rate_trend: str  # 'RISING', 'FALLING', 'STABLE'
    open_interest: float  # Total OI in contracts
    oi_change_24h: float  # % change in last 24h
    long_short_ratio: float  # Long/Short account ratio
    liquidation_risk: str  # 'LOW', 'MEDIUM', 'HIGH'
    sentiment_score: float  # -1.0 to +1.0 derived from derivatives data
    confidence: float
    timeframe: Optional[str] = None


class DerivativesAnalyzer:
    def __init__(self, binance_client, config=None):
        """
        Initialize Derivatives Analyzer with multi-TF support.
        
        Args:
            binance_client: Binance futures client
            config: Application configuration
        """
        self.client = binance_client
        self.config = config
        
        # Funding rate thresholds
        self.HIGH_FUNDING_RATE = 0.01  # 1% per 8 hours = extreme
        self.LOW_FUNDING_RATE = -0.01  # -1% = very bearish
        
        # OI change thresholds
        self.OI_SIGNIFICANT_CHANGE = 0.15  # 15% change is significant
        
        # Timeframes for analysis (different lookback periods)
        self.timeframes = ['1h', '15m', '5m']
        if config and hasattr(config, 'get_list'):
            self.timeframes = config.get_list('MULTITF', 'timeframe_hierarchy',
                                              fallback=['1h', '15m', '5m'])
        
        # Aggregator for multi-TF results
        self.aggregator = MultiTFContextAggregator(config) if config else MultiTFContextAggregator()
        
        logger.info(f"DerivativesAnalyzer initialized with multi-TF support: {self.timeframes}")
    
    def analyze(self, symbol: str, context: Optional[AnalysisContext] = None) -> Dict:
        """
        Analyze derivatives metrics with multi-timeframe support.
        
        Returns comprehensive view of futures market conditions across multiple timeframes.
        """
        try:
            # For derivatives, we analyze different time windows instead of candle TFs
            # Collect data for different lookback periods
            tf_data = self._collect_timeframe_data(symbol)
            
            if not tf_data:
                return {
                    "error": "No derivatives data available",
                    "confidence": 0.0
                }
            
            # Analyze each timeframe separately
            per_timeframe_results = {}
            
            for tf, data in tf_data.items():
                result = self._analyze_single_timeframe(symbol, tf, data)
                if result and 'error' not in result:
                    per_timeframe_results[tf] = result
            
            if not per_timeframe_results:
                return {
                    "error": "Analysis failed on all timeframes",
                    "confidence": 0.0
                }
            
            # Aggregate results using MultiTFContextAggregator
            tf_analysis_for_aggregator = {}
            for tf, result in per_timeframe_results.items():
                # Determine trend from sentiment score
                sentiment = result.get('sentiment_score', 0)
                trend = 1 if sentiment > 0.2 else (-1 if sentiment < -0.2 else 0)
                
                tf_analysis_for_aggregator[tf] = {
                    'trend': trend,
                    'trend_strength': abs(sentiment),
                    'support': 0,  # Derivatives don't provide S/R levels
                    'resistance': 0,
                    'volume_score': result.get('confidence', 0),
                    'atr': 0,
                    'confidence': result.get('confidence', 0)
                }
            
            # Create aggregated context
            if context:
                multi_tf_context = self.aggregator.aggregate(tf_analysis_for_aggregator, symbol)
                
                final_result = {
                    "timeframes_analyzed": list(per_timeframe_results.keys()),
                    "per_timeframe_results": per_timeframe_results,
                    "multi_tf_context": {
                        "dominant_trend": multi_tf_context.dominant_trend,
                        "trend_alignment": multi_tf_context.trend_alignment,
                        "composite_confidence": multi_tf_context.composite_confidence,
                        "trend_conflicts": multi_tf_context.trend_conflicts
                    },
                    "aggregate_sentiment": np.mean([r['sentiment_score'] for r in per_timeframe_results.values()]),
                    "aggregate_liquidation_risk": self._get_dominant_risk(per_timeframe_results),
                    "confidence": multi_tf_context.composite_confidence,
                    "lineage": multi_tf_context.lineage
                }
                
                context.add_result("Derivatives", final_result, multi_tf_context.lineage)
            else:
                # Fallback without context
                final_result = {
                    "timeframes_analyzed": list(per_timeframe_results.keys()),
                    "per_timeframe_results": per_timeframe_results,
                    "aggregate_sentiment": np.mean([r['sentiment_score'] for r in per_timeframe_results.values()]),
                    "aggregate_liquidation_risk": self._get_dominant_risk(per_timeframe_results),
                    "confidence": np.mean([r['confidence'] for r in per_timeframe_results.values()])
                }
            
            return final_result
            
        except Exception as e:
            logger.error(f"Error analyzing derivatives for {symbol}: {e}")
            return {
                "error": str(e),
                "confidence": 0.0
            }
    
    def _collect_timeframe_data(self, symbol: str) -> Dict[str, Dict]:
        """
        Collect derivatives data for different time windows.
        Returns: dict {timeframe: data_dict}
        """
        tf_data = {}
        
        # Get funding rate history
        funding_rates = self._get_funding_rates(symbol)
        
        # Get open interest data
        oi_data = self._get_open_interest(symbol)
        
        # Get long/short ratio
        ls_ratio = self._get_long_short_ratio(symbol)
        
        # Create different time windows for analysis
        if funding_rates and len(funding_rates.get('rates', [])) >= 9:
            # 1h window: last 3 funding rates (24 hours)
            tf_data['1h'] = {
                'funding_rates': funding_rates['rates'][-3:],
                'oi_data': oi_data,
                'ls_ratio': ls_ratio
            }
        
        if funding_rates and len(funding_rates.get('rates', [])) >= 6:
            # 15m window: last 6 funding rates (more recent)
            tf_data['15m'] = {
                'funding_rates': funding_rates['rates'][-6:],
                'oi_data': oi_data,
                'ls_ratio': ls_ratio
            }
        
        # 5m window: most recent data point
        if funding_rates:
            tf_data['5m'] = {
                'funding_rates': funding_rates['rates'][-1:],
                'oi_data': oi_data,
                'ls_ratio': ls_ratio
            }
        
        return tf_data
    
    def _analyze_single_timeframe(self, symbol: str, timeframe: str, data: Dict) -> Dict:
        """Analyze derivatives metrics for a single timeframe window."""
        try:
            funding_rates = data.get('funding_rates', [])
            oi_data = data.get('oi_data')
            ls_ratio = data.get('ls_ratio')
            
            current_funding = funding_rates[-1] if funding_rates else 0.0
            funding_trend = self._analyze_funding_trend({'rates': funding_rates})
            
            current_oi = oi_data['current'] if oi_data else 0.0
            oi_change = oi_data['change_24h'] if oi_data else 0.0
            
            # Determine liquidation risk
            liquidation_risk = self._assess_liquidation_risk(
                funding_rate=current_funding,
                oi_change=oi_change,
                long_short=ls_ratio
            )
            
            # Calculate sentiment score
            sentiment = self._calculate_sentiment(
                funding_rate=current_funding,
                funding_trend=funding_trend,
                oi_change=oi_change,
                long_short=ls_ratio
            )
            
            # Confidence based on data availability
            confidence = self._calculate_confidence(
                has_funding=bool(funding_rates),
                has_oi=oi_data is not None,
                has_ls=ls_ratio is not None
            )
            
            lineage = LineageTracker.create_calculated(
                method=f"derivatives_analysis_{timeframe}",
                dependencies=[],
                quality=DataQuality.MEDIUM if confidence > 0.5 else DataQuality.LOW,
                metadata={
                    'timeframe': timeframe,
                    'funding_rate': current_funding,
                    'sentiment': sentiment
                }
            )
            
            return {
                "funding_rate": round(current_funding, 6),
                "funding_rate_trend": funding_trend,
                "open_interest": round(current_oi, 2),
                "oi_change_24h": round(oi_change, 4),
                "long_short_ratio": round(ls_ratio, 4) if ls_ratio else 1.0,
                "liquidation_risk": liquidation_risk,
                "sentiment_score": round(sentiment, 4),
                "confidence": round(confidence, 4),
                "timeframe": timeframe,
                "lineage": lineage
            }
            
        except Exception as e:
            logger.warning(f"Error analyzing {timeframe} for {symbol}: {e}")
            return {"error": str(e), "confidence": 0.0, "timeframe": timeframe}
    
    def _get_dominant_risk(self, per_timeframe_results: Dict) -> str:
        """Get the highest risk level across all timeframes."""
        risk_order = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1, 'UNKNOWN': 0}
        risks = [r.get('liquidation_risk', 'UNKNOWN') for r in per_timeframe_results.values()]
        
        if not risks:
            return 'UNKNOWN'
        
        return max(risks, key=lambda x: risk_order.get(x, 0))
    
    def _get_funding_rates(self, symbol: str) -> Optional[Dict]:
        """Get funding rate history."""
        try:
            # Last 3 days of funding rates (9 data points for 8-hour intervals)
            klines = self.client.futures_funding_rate(
                symbol=symbol,
                limit=100
            )
            
            if not klines:
                return None
            
            rates = [float(k['fundingRate']) for k in klines]
            timestamps = [k['fundingTime'] for k in klines]
            
            current_rate = rates[-1] if rates else 0.0
            
            # Calculate average of last 3 rates
            avg_recent = np.mean(rates[-3:]) if len(rates) >= 3 else current_rate
            
            return {
                'current': current_rate,
                'recent_avg': avg_recent,
                'rates': rates,
                'timestamps': timestamps
            }
        except Exception as e:
            logger.warning(f"Could not get funding rates for {symbol}: {e}")
            return None
    
    def _get_open_interest(self, symbol: str) -> Optional[Dict]:
        """Get open interest data."""
        try:
            # Current open interest
            ticker = self.client.futures_ticker(symbol=symbol)
            current_oi = float(ticker.get('openInterest', 0))
            
            # Get historical OI (if available via API)
            # For now, estimate from price action
            # In production, would use futures_oi_history endpoint
            
            return {
                'current': current_oi,
                'change_24h': 0.0  # Would calculate from history
            }
        except Exception as e:
            logger.warning(f"Could not get OI for {symbol}: {e}")
            return None
    
    def _get_long_short_ratio(self, symbol: str) -> Optional[float]:
        """Get long/short account ratio."""
        try:
            # Top trader long/short ratio
            data = self.client.futures_top_longshort_account_ratio(
                symbol=symbol,
                period='5m',
                limit=10
            )
            
            if data:
                ratios = [float(d['longShortRatio']) for d in data]
                return np.mean(ratios[-5:])  # Average of last 5 periods
            
            return None
        except Exception as e:
            logger.debug(f"Could not get L/S ratio for {symbol}: {e}")
            return None
    
    def _analyze_funding_trend(self, funding_data: Optional[Dict]) -> str:
        """Analyze funding rate trend."""
        if not funding_data or len(funding_data.get('rates', [])) < 3:
            return 'STABLE'
        
        rates = funding_data['rates'][-5:]
        
        # Simple trend analysis
        if rates[-1] > rates[0] * 1.2:
            return 'RISING'
        elif rates[-1] < rates[0] * 0.8:
            return 'FALLING'
        else:
            return 'STABLE'
    
    def _assess_liquidation_risk(
        self,
        funding_rate: float,
        oi_change: float,
        long_short: Optional[float]
    ) -> str:
        """Assess risk of mass liquidations."""
        risk_factors = 0
        
        # High funding rate = overleveraged longs
        if funding_rate > self.HIGH_FUNDING_RATE:
            risk_factors += 2
        elif funding_rate > 0.005:
            risk_factors += 1
        
        # Negative funding = overleveraged shorts
        if funding_rate < self.LOW_FUNDING_RATE:
            risk_factors += 2
        elif funding_rate < -0.005:
            risk_factors += 1
        
        # Rapid OI increase = new leverage entering
        if abs(oi_change) > 0.3:
            risk_factors += 2
        elif abs(oi_change) > 0.15:
            risk_factors += 1
        
        # Extreme long/short ratio
        if long_short:
            if long_short > 2.0 or long_short < 0.5:
                risk_factors += 1
        
        # Determine risk level
        if risk_factors >= 4:
            return 'HIGH'
        elif risk_factors >= 2:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def _calculate_sentiment(
        self,
        funding_rate: float,
        funding_trend: str,
        oi_change: float,
        long_short: Optional[float]
    ) -> float:
        """
        Calculate sentiment score from derivatives data.
        
        Positive sentiment:
        - Rising OI with positive funding (bulls confident)
        - Long/short ratio > 1 but not extreme
        
        Negative sentiment:
        - Very high funding (overcrowded longs = squeeze risk)
        - Falling OI with negative funding (bears dominant)
        """
        sentiment = 0.0
        
        # Funding rate contribution (moderate positive = bullish)
        if 0 < funding_rate < 0.005:
            sentiment += 0.3  # Healthy bullish
        elif funding_rate > 0.01:
            sentiment -= 0.4  # Overcrowded longs = danger
        elif -0.005 < funding_rate < 0:
            sentiment -= 0.2  # Slightly bearish
        elif funding_rate < -0.01:
            sentiment += 0.3  # Overcrowded shorts = squeeze potential
        
        # OI change contribution
        if oi_change > 0.1:
            sentiment += 0.2  # Growing interest
        elif oi_change < -0.1:
            sentiment -= 0.2  # Declining interest
        
        # Long/short ratio
        if long_short:
            if 1.0 < long_short < 1.5:
                sentiment += 0.2  # Healthy long bias
            elif long_short > 2.0:
                sentiment -= 0.3  # Too many longs
            elif 0.7 < long_short < 1.0:
                sentiment -= 0.1  # Slight short bias
            elif long_short < 0.5:
                sentiment += 0.3  # Too many shorts = squeeze
        
        return max(-1.0, min(1.0, sentiment))
    
    def _calculate_confidence(
        self,
        has_funding: bool,
        has_oi: bool,
        has_ls: bool
    ) -> float:
        """Calculate confidence based on data availability."""
        score = 0.0
        
        if has_funding:
            score += 0.4
        if has_oi:
            score += 0.3
        if has_ls:
            score += 0.3
        
        return score
    
    def _empty_metrics(self) -> DerivativesMetrics:
        """Return empty metrics when data unavailable."""
        return DerivativesMetrics(
            funding_rate=0.0,
            funding_rate_trend='UNKNOWN',
            open_interest=0.0,
            oi_change_24h=0.0,
            long_short_ratio=1.0,
            liquidation_risk='UNKNOWN',
            sentiment_score=0.0,
            confidence=0.0
        )
    
    def get_signal(self, metrics: DerivativesMetrics) -> Tuple[float, float]:
        """
        Generate trading signal from derivatives metrics.
        
        Returns:
            score: -1.0 to +1.0
            confidence: 0.0 to 1.0
        """
        if metrics.confidence < 0.3:
            return 0.0, 0.0
        
        score = metrics.sentiment_score * 0.5  # Scale down influence
        confidence = metrics.confidence
        
        # Adjust for liquidation risk
        if metrics.liquidation_risk == 'HIGH':
            # High risk = be cautious, reduce position size signal
            confidence *= 0.7
        
        return score, confidence
