"""
TENBID v2.0 - News Sentiment Analyzer
Модуль анализа новостного фона и его влияния на рынок.
Собирает данные из реальных RSS-лент и API, выдает вектор влияния.
Без эмуляции и домыслов — только честные данные.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import hashlib

# Заглушки для внешних библиотек (будут заменены на реальные при наличии)
try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

logger = logging.getLogger(__name__)

@dataclass
class NewsItem:
    """Отдельная новость"""
    title: str
    summary: str
    source: str
    published_at: datetime
    url: str
    sentiment_score: float = 0.0  # -1.0 (негатив) до 1.0 (позитив)
    impact_strength: float = 0.0  # 0.0 (слабое) до 1.0 (сильное)
    expected_duration: timedelta = timedelta(hours=1)
    keywords: List[str] = field(default_factory=list)
    id: str = ""
    
    def __post_init__(self):
        if not self.id:
            self.id = hashlib.md5(f"{self.title}{self.published_at}".encode()).hexdigest()[:12]

@dataclass
class SentimentVector:
    """Вектор влияния новостей на рынок"""
    direction: int = 0  # -1 (медвежий), 0 (нейтральный), 1 (бычий)
    strength: float = 0.0  # 0.0 - 1.0
    confidence: float = 0.0  # Уверенность в оценке
    duration_hours: float = 1.0  # Ожидаемая длительность влияния
    dominant_topics: List[str] = field(default_factory=list)
    recent_news_count: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict:
        return {
            "direction": self.direction,
            "strength": self.strength,
            "confidence": self.confidence,
            "duration_hours": self.duration_hours,
            "dominant_topics": self.dominant_topics,
            "recent_news_count": self.recent_news_count,
            "timestamp": self.timestamp.isoformat()
        }

class NewsSentimentAnalyzer:
    """
    Анализатор новостного сентимента.
    Парсит RSS-ленты, оценивает влияние новостей на крипторынок.
    """
    
    # Ключевые слова для классификации новостей
    BULLISH_KEYWORDS = [
        'adoption', 'partnership', 'upgrade', 'bullish', 'surge', 'rally', 
        'record high', 'institutional', 'approval', 'etf', 'integration',
        'growth', 'positive', 'breakthrough', 'milestone'
    ]
    
    BEARISH_KEYWORDS = [
        'ban', 'crackdown', 'hack', 'exploit', 'lawsuit', 'bearish', 'crash',
        'plunge', 'sell-off', 'negative', 'regulation', 'fraud', 'scam',
        'security breach', 'loss', 'decline', 'warning'
    ]
    
    HIGH_IMPACT_TOPICS = [
        'fed', 'interest rate', 'inflation', 'sec', 'regulation',
        'bitcoin etf', 'halving', 'major exchange', 'binance', 'coinbase'
    ]
    
    def __init__(self, rss_feeds: Optional[List[str]] = None):
        """
        Инициализация анализатора.
        
        Args:
            rss_feeds: Список URL RSS-лент (CryptoPanic, CoinDesk, etc.)
        """
        self.rss_feeds = rss_feeds or [
            "https://cryptopanic.com/feed/",
            "https://www.coindesk.com/arc/outboundfeeds/rss/",
            "https://cointelegraph.com/rss"
        ]
        self.news_cache: List[NewsItem] = []
        self.max_cache_size = 100
        self.last_update: Optional[datetime] = None
        
        if not HAS_FEEDPARSER:
            logger.warning("feedparser не установлен. Новости будут работать в демо-режиме.")
        
        logger.info(f"NewsSentimentAnalyzer инициализирован с {len(self.rss_feeds)} источниками")
    
    def fetch_news(self, limit: int = 50) -> List[NewsItem]:
        """
        Получение новостей из RSS-лент.
        
        Args:
            limit: Максимальное количество новостей для загрузки
            
        Returns:
            Список NewsItem
        """
        if not HAS_FEEDPARSER:
            logger.debug("feedparser недоступен, возврат пустого списка новостей")
            return []
        
        fetched_news = []
        
        for feed_url in self.rss_feeds:
            try:
                feed = feedparser.parse(feed_url)
                
                for entry in feed.entries[:limit // len(self.rss_feeds) + 1]:
                    published = datetime.utcnow()
                    
                    # Парсинг времени публикации
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        try:
                            published = datetime(*entry.published_parsed[:6])
                        except:
                            pass
                    
                    news_item = NewsItem(
                        title=entry.get('title', 'No Title'),
                        summary=entry.get('summary', entry.get('description', '')),
                        source=feed_url,
                        published_at=published,
                        url=entry.get('link', ''),
                        keywords=self._extract_keywords(entry.get('title', '') + ' ' + entry.get('summary', ''))
                    )
                    
                    # Оценка сентимента
                    news_item.sentiment_score = self._calculate_sentiment(news_item.title + ' ' + news_item.summary)
                    news_item.impact_strength = self._calculate_impact(news_item)
                    news_item.expected_duration = self._estimate_duration(news_item)
                    
                    fetched_news.append(news_item)
                    
            except Exception as e:
                logger.error(f"Ошибка при парсинге ленты {feed_url}: {e}")
        
        # Сортировка по времени
        fetched_news.sort(key=lambda x: x.published_at, reverse=True)
        
        # Обновление кэша
        self.news_cache = fetched_news[:self.max_cache_size]
        self.last_update = datetime.utcnow()
        
        logger.info(f"Загружено {len(fetched_news)} новостей")
        return fetched_news
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Извлечение ключевых слов из текста"""
        text_lower = text.lower()
        keywords = []
        
        all_keywords = self.BULLISH_KEYWORDS + self.BEARISH_KEYWORDS + self.HIGH_IMPACT_TOPICS
        
        for keyword in all_keywords:
            if keyword in text_lower:
                keywords.append(keyword)
        
        return list(set(keywords))
    
    def _calculate_sentiment(self, text: str) -> float:
        """
        Расчет сентимента текста.
        
        Returns:
            float от -1.0 (негатив) до 1.0 (позитив)
        """
        text_lower = text.lower()
        
        bullish_count = sum(1 for kw in self.BULLISH_KEYWORDS if kw in text_lower)
        bearish_count = sum(1 for kw in self.BEARISH_KEYWORDS if kw in text_lower)
        
        total = bullish_count + bearish_count
        if total == 0:
            return 0.0
        
        score = (bullish_count - bearish_count) / total
        return max(-1.0, min(1.0, score))
    
    def _calculate_impact(self, news: NewsItem) -> float:
        """
        Расчет силы влияния новости.
        
        Returns:
            float от 0.0 (слабое) до 1.0 (сильное)
        """
        impact = 0.0
        
        # Влияние ключевых тем
        high_impact_matches = sum(1 for topic in self.HIGH_IMPACT_TOPICS if topic in news.title.lower())
        impact += min(0.5, high_impact_matches * 0.15)
        
        # Влияние количества ключевых слов
        keyword_ratio = len(news.keywords) / 10.0
        impact += min(0.3, keyword_ratio)
        
        # Свежесть новости (более свежие имеют большее влияние)
        hours_since_publish = (datetime.utcnow() - news.published_at).total_seconds() / 3600
        freshness_factor = max(0.0, 1.0 - (hours_since_publish / 24.0))
        impact += freshness_factor * 0.2
        
        return min(1.0, impact)
    
    def _estimate_duration(self, news: NewsItem) -> timedelta:
        """Оценка длительности влияния новости"""
        if any(topic in news.title.lower() for topic in ['fed', 'interest rate', 'regulation', 'etf']):
            return timedelta(hours=24)  # Долгосрочное влияние
        
        if news.impact_strength > 0.7:
            return timedelta(hours=6)
        elif news.impact_strength > 0.4:
            return timedelta(hours=3)
        else:
            return timedelta(hours=1)
    
    def get_sentiment_vector(self, time_window: timedelta = timedelta(hours=2)) -> SentimentVector:
        """
        Получение агрегированного вектора сентимента.
        
        Args:
            time_window: Временное окно для анализа
            
        Returns:
            SentimentVector с обобщенной оценкой
        """
        # Обновление новостей если нужно
        if not self.news_cache or not self.last_update or \
           (datetime.utcnow() - self.last_update) > timedelta(minutes=10):
            self.fetch_news()
        
        if not self.news_cache:
            return SentimentVector()
        
        # Фильтрация новостей по временному окну
        cutoff_time = datetime.utcnow() - time_window
        recent_news = [n for n in self.news_cache if n.published_at >= cutoff_time]
        
        if not recent_news:
            return SentimentVector()
        
        # Агрегация сентимента
        total_sentiment = sum(n.sentiment_score * n.impact_strength for n in recent_news)
        total_impact = sum(n.impact_strength for n in recent_news)
        
        if total_impact == 0:
            return SentimentVector()
        
        avg_sentiment = total_sentiment / total_impact
        
        # Определение направления
        direction = 0
        if avg_sentiment > 0.1:
            direction = 1
        elif avg_sentiment < -0.1:
            direction = -1
        
        # Расчет уверенности
        confidence = min(1.0, len(recent_news) / 10.0) * total_impact
        
        # Доминирующие темы
        topic_counts = {}
        for news in recent_news:
            for keyword in news.keywords:
                topic_counts[keyword] = topic_counts.get(keyword, 0) + 1
        
        dominant_topics = sorted(topic_counts.keys(), key=lambda x: topic_counts[x], reverse=True)[:5]
        
        # Средняя длительность
        avg_duration = sum(n.expected_duration.total_seconds() for n in recent_news) / len(recent_news)
        
        vector = SentimentVector(
            direction=direction,
            strength=min(1.0, abs(avg_sentiment)),
            confidence=confidence,
            duration_hours=avg_duration / 3600,
            dominant_topics=dominant_topics,
            recent_news_count=len(recent_news)
        )
        
        logger.debug(f"Вектор сентимента: Direction={vector.direction}, Strength={vector.strength:.2f}, Confidence={vector.confidence:.2f}")
        
        return vector
    
    def get_analysis_id(self, vector: SentimentVector) -> str:
        """Генерация уникального ID для анализа"""
        data_str = f"{vector.timestamp.isoformat()}{vector.direction}{vector.strength}"
        return hashlib.md5(data_str.encode()).hexdigest()[:12]
