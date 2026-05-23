"""
News Aggregator - Sentiment Analysis with Impact Scoring.

CRITICAL REQUIREMENTS:
1. News acts ONLY as MODIFIER (coefficient 0.3), NOT additive component
2. NO global trading pause on news - system can trade if TA confirms
3. Impact Score decays over time
4. Works as confidence modifier, not trigger
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class NewsItem:
    """Individual news item with sentiment."""
    headline: str
    source: str
    timestamp: float
    sentiment_score: float  # -1.0 (very negative) to +1.0 (very positive)
    impact_score: float  # 0.0 to 1.0 (after decay)
    related_symbols: List[str]
    category: str  # 'REGULATION', 'ADOPTION', 'MARKET', 'TECHNOLOGY', 'OTHER'

@dataclass
class NewsAggregationResult:
    """Aggregated news sentiment for decision making."""
    overall_sentiment: float  # -1.0 to +1.0
    overall_confidence: float  # 0.0 to 1.0
    news_count: int
    dominant_category: str
    recent_impact: float  # Weighted impact of last hour
    modifier_value: float  # Final modifier (-0.3 to +0.3)

class NewsAggregator:
    def __init__(self):
        """
        Initialize News Aggregator.
        
        CRITICAL: News modifies TA signals, does not drive decisions alone.
        """
        self.news_buffer: List[NewsItem] = []
        self.max_news_age_hours = 24
        
        # CRITICAL: News modifier coefficient (max 30% influence)
        self.NEWS_MODIFIER_COEFFICIENT = 0.3
        
        # Decay rate per hour (how fast news loses impact)
        self.DECAY_RATE_PER_HOUR = 0.15
        
        # Minimum sentiment threshold to consider
        self.MIN_SENTIMENT_IMPACT = 0.2
        
        logger.info(f"NewsAggregator initialized (modifier_coefficient={self.NEWS_MODIFIER_COEFFICIENT})")
    
    def add_news(
        self,
        headline: str,
        source: str,
        sentiment_score: float,
        related_symbols: List[str],
        category: str = 'OTHER'
    ):
        """Add a new news item to the buffer."""
        now = datetime.now().timestamp()
        
        # Calculate initial impact based on category and sentiment
        base_impact = self._calculate_base_impact(sentiment_score, category)
        
        news_item = NewsItem(
            headline=headline,
            source=source,
            timestamp=now,
            sentiment_score=sentiment_score,
            impact_score=base_impact,
            related_symbols=related_symbols,
            category=category
        )
        
        self.news_buffer.append(news_item)
        logger.debug(f"Added news: {headline[:50]}... (sentiment={sentiment_score}, impact={base_impact})")
        
        # Cleanup old news
        self._cleanup_old_news()
    
    def _calculate_base_impact(self, sentiment: float, category: str) -> float:
        """Calculate initial impact score based on category and sentiment."""
        # Category multipliers
        category_weights = {
            'REGULATION': 1.5,    # Regulatory news has high impact
            'ADOPTION': 1.3,      # Adoption news is significant
            'MARKET': 1.0,        # General market news
            'TECHNOLOGY': 1.2,    # Tech developments
            'OTHER': 0.8          # Other news
        }
        
        weight = category_weights.get(category, 1.0)
        
        # Base impact from sentiment magnitude
        base = abs(sentiment) * weight
        
        # Clamp to 0-1 range
        return min(1.0, max(0.0, base))
    
    def _cleanup_old_news(self):
        """Remove news older than max_news_age_hours."""
        cutoff = datetime.now().timestamp() - (self.max_news_age_hours * 3600)
        self.news_buffer = [n for n in self.news_buffer if n.timestamp > cutoff]
    
    def apply_decay(self):
        """Apply time decay to all news items."""
        now = datetime.now().timestamp()
        
        for news in self.news_buffer:
            age_hours = (now - news.timestamp) / 3600
            
            # Exponential decay
            decay_factor = np.exp(-self.DECAY_RATE_PER_HOUR * age_hours)
            news.impact_score *= decay_factor
    
    def get_aggregated_sentiment(self, symbol: str = None) -> NewsAggregationResult:
        """
        Get aggregated news sentiment for a symbol or overall.
        
        CRITICAL: Returns modifier value (-0.3 to +0.3) for use in strategy.
        Formula: modifier = sentiment * confidence * 0.3
        """
        # Apply decay first
        self.apply_decay()
        
        # Filter relevant news
        if symbol:
            relevant_news = [
                n for n in self.news_buffer 
                if symbol in n.related_symbols or 'ALL' in n.related_symbols
            ]
        else:
            relevant_news = self.news_buffer
        
        if not relevant_news:
            return NewsAggregationResult(
                overall_sentiment=0.0,
                overall_confidence=0.0,
                news_count=0,
                dominant_category='NONE',
                recent_impact=0.0,
                modifier_value=0.0
            )
        
        # Calculate weighted average sentiment
        total_weight = sum(n.impact_score for n in relevant_news)
        
        if total_weight == 0:
            return NewsAggregationResult(
                overall_sentiment=0.0,
                overall_confidence=0.0,
                news_count=len(relevant_news),
                dominant_category='NONE',
                recent_impact=0.0,
                modifier_value=0.0
            )
        
        weighted_sentiment = sum(
            n.sentiment_score * n.impact_score for n in relevant_news
        ) / total_weight
        
        # Confidence based on number of sources and recency
        confidence = self._calculate_confidence(relevant_news)
        
        # Find dominant category
        category_counts = {}
        for n in relevant_news:
            category_counts[n.category] = category_counts.get(n.category, 0) + n.impact_score
        dominant_category = max(category_counts, key=category_counts.get) if category_counts else 'NONE'
        
        # Calculate recent impact (last hour)
        one_hour_ago = datetime.now().timestamp() - 3600
        recent_news = [n for n in relevant_news if n.timestamp > one_hour_ago]
        recent_impact = sum(n.impact_score for n in recent_news) / max(1, len(recent_news))
        
        # CRITICAL: Calculate modifier (bounded to [-0.3, +0.3])
        # Formula: modifier = sentiment * confidence * 0.3
        modifier = weighted_sentiment * confidence * self.NEWS_MODIFIER_COEFFICIENT
        modifier = max(-0.3, min(0.3, modifier))
        
        result = NewsAggregationResult(
            overall_sentiment=round(weighted_sentiment, 4),
            overall_confidence=round(confidence, 4),
            news_count=len(relevant_news),
            dominant_category=dominant_category,
            recent_impact=round(recent_impact, 4),
            modifier_value=round(modifier, 4)
        )
        
        logger.debug(
            f"News aggregation: sentiment={weighted_sentiment:.3f}, "
            f"conf={confidence:.3f}, modifier={modifier:.3f}, count={len(relevant_news)}"
        )
        
        return result
    
    def _calculate_confidence(self, news_list: List[NewsItem]) -> float:
        """
        Calculate confidence in aggregated sentiment.
        
        Factors:
        - Number of news items (more = higher confidence)
        - Recency (newer = higher confidence)
        - Source diversity (more sources = higher confidence)
        """
        if not news_list:
            return 0.0
        
        # Base confidence from count (logarithmic scale)
        count_factor = min(1.0, np.log(len(news_list) + 1) / np.log(10))
        
        # Recency factor
        now = datetime.now().timestamp()
        avg_age_hours = np.mean([(now - n.timestamp) / 3600 for n in news_list])
        recency_factor = np.exp(-0.1 * avg_age_hours)  # Decay with age
        
        # Source diversity
        unique_sources = len(set(n.source for n in news_list))
        source_factor = min(1.0, unique_sources / 5.0)  # Max at 5 sources
        
        # Combined confidence
        confidence = (count_factor * 0.4 + recency_factor * 0.4 + source_factor * 0.2)
        
        return min(1.0, max(0.0, confidence))
    
    def get_modifier_for_strategy(
        self,
        symbol: str = None,
        ta_signal_strength: float = 0.0
    ) -> Tuple[float, float]:
        """
        Get news modifier for strategy decision.
        
        CRITICAL: This is the ONLY method strategy should call.
        
        Returns:
            modifier_value: Value to add to base TA score (-0.3 to +0.3)
            confidence: Confidence in this modifier
        """
        result = self.get_aggregated_sentiment(symbol)
        
        # If TA signal is weak, reduce news impact further
        if abs(ta_signal_strength) < 0.3:
            # TA is unclear, don't let news dominate
            reduction_factor = 0.5
            modifier = result.modifier_value * reduction_factor
            confidence = result.overall_confidence * reduction_factor
        else:
            modifier = result.modifier_value
            confidence = result.overall_confidence
        
        logger.debug(
            f"News modifier for strategy: {modifier:.4f} (conf: {confidence:.4f})"
        )
        
        return modifier, confidence
    
    def clear_buffer(self):
        """Clear all news (useful for testing)."""
        self.news_buffer = []
        logger.info("News buffer cleared")
