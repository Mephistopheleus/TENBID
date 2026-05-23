"""
Derivatives Analyzer - Funding Rate and Open Interest Analysis.

Analyzes futures market data:
- Funding Rate (cost of holding positions)
- Open Interest (total outstanding contracts)
- Long/Short Ratio
- Liquidation heatmaps

These metrics provide insight into market sentiment and potential squeeze scenarios.
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

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

class DerivativesAnalyzer:
    def __init__(self, binance_client):
        """
        Initialize Derivatives Analyzer.
        
        Args:
            binance_client: Binance futures client
        """
        self.client = binance_client
        
        # Funding rate thresholds
        self.HIGH_FUNDING_RATE = 0.01  # 1% per 8 hours = extreme
        self.LOW_FUNDING_RATE = -0.01  # -1% = very bearish
        
        # OI change thresholds
        self.OI_SIGNIFICANT_CHANGE = 0.15  # 15% change is significant
        
        logger.info("DerivativesAnalyzer initialized")
    
    def analyze(self, symbol: str) -> DerivativesMetrics:
        """
        Analyze derivatives metrics for a symbol.
        
        Returns comprehensive view of futures market conditions.
        """
        try:
            # Get funding rate history
            funding_rates = self._get_funding_rates(symbol)
            
            # Get open interest data
            oi_data = self._get_open_interest(symbol)
            
            # Get long/short ratio
            ls_ratio = self._get_long_short_ratio(symbol)
            
            # Calculate metrics
            current_funding = funding_rates['current'] if funding_rates else 0.0
            funding_trend = self._analyze_funding_trend(funding_rates)
            
            current_oi = oi_data['current'] if oi_data else 0.0
            oi_change = oi_data['change_24h'] if oi_data else 0.0
            
            # Determine liquidation risk
            liquidation_risk = self._assess_liquidation_risk(
                funding_rate=current_funding,
                oi_change=oi_change,
                long_short=ls_ratio
            )
            
            # Calculate sentiment score from derivatives data
            sentiment = self._calculate_sentiment(
                funding_rate=current_funding,
                funding_trend=funding_trend,
                oi_change=oi_change,
                long_short=ls_ratio
            )
            
            # Confidence based on data availability
            confidence = self._calculate_confidence(
                has_funding=funding_rates is not None,
                has_oi=oi_data is not None,
                has_ls=ls_ratio is not None
            )
            
            return DerivativesMetrics(
                funding_rate=round(current_funding, 6),
                funding_rate_trend=funding_trend,
                open_interest=round(current_oi, 2),
                oi_change_24h=round(oi_change, 4),
                long_short_ratio=round(ls_ratio, 4) if ls_ratio else 1.0,
                liquidation_risk=liquidation_risk,
                sentiment_score=round(sentiment, 4),
                confidence=round(confidence, 4)
            )
            
        except Exception as e:
            logger.error(f"Error analyzing derivatives for {symbol}: {e}")
            return self._empty_metrics()
    
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
