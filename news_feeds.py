"""
News Feeds — Crypto News Aggregation
======================================
Collects news from multiple free sources:
- NewsAPI (free tier: 100 requests/day)
- Finnhub (free tier: 60 API calls/min)
- CoinGecko status/trending
- RSS-style crypto news
"""

import os
import time
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("news_feeds")


class NewsFeedManager:
    """Aggregates crypto news from multiple free sources."""

    def __init__(self):
        self.newsapi_key = os.getenv("NEWSAPI_KEY", "")
        self.finnhub_key = os.getenv("FINNHUB_API_KEY", "")
        self._cache = {}
        self._cache_ttl = {}

    def _cached(self, key: str, ttl: int = 120):
        if key in self._cache and key in self._cache_ttl:
            if time.time() - self._cache_ttl[key] < ttl:
                return self._cache[key]
        return None

    def _set_cache(self, key: str, data):
        self._cache[key] = data
        self._cache_ttl[key] = time.time()

    # ─── NewsAPI ─────────────────────────────────

    def get_crypto_news(self, query: str = "cryptocurrency bitcoin ethereum",
                        max_results: int = 10) -> List[Dict]:
        """Get crypto news from NewsAPI."""
        cached = self._cached(f"newsapi_{query}", ttl=300)
        if cached:
            return cached

        if not self.newsapi_key:
            return []

        try:
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": max_results,
                "apiKey": self.newsapi_key,
            }
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                articles = resp.json().get("articles", [])
                result = []
                for a in articles:
                    result.append({
                        "title": a.get("title", ""),
                        "description": a.get("description", ""),
                        "source": a.get("source", {}).get("name", "Unknown"),
                        "published": a.get("publishedAt", ""),
                        "url": a.get("url", ""),
                    })
                self._set_cache(f"newsapi_{query}", result)
                return result
        except Exception as e:
            logger.debug(f"NewsAPI error: {e}")
        return []

    # ─── Finnhub ─────────────────────────────────

    def get_finnhub_news(self, category: str = "crypto") -> List[Dict]:
        """Get market news from Finnhub."""
        cached = self._cached("finnhub_news", ttl=300)
        if cached:
            return cached

        if not self.finnhub_key:
            return []

        try:
            url = "https://finnhub.io/api/v1/news"
            params = {
                "category": category,
                "token": self.finnhub_key,
            }
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                result = []
                for item in data[:10]:
                    result.append({
                        "title": item.get("headline", ""),
                        "description": item.get("summary", "")[:200],
                        "source": item.get("source", "Unknown"),
                        "published": datetime.fromtimestamp(
                            item.get("datetime", 0)
                        ).isoformat(),
                        "url": item.get("url", ""),
                    })
                self._set_cache("finnhub_news", result)
                return result
        except Exception as e:
            logger.debug(f"Finnhub error: {e}")
        return []

    # ─── CryptoCompare (free, no key needed) ─────

    def get_cryptocompare_news(self) -> List[Dict]:
        """Get latest crypto news from CryptoCompare (free, no API key)."""
        cached = self._cached("cryptocompare", ttl=300)
        if cached:
            return cached

        try:
            url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json().get("Data", [])
                result = []
                for item in data[:15]:
                    result.append({
                        "title": item.get("title", ""),
                        "description": item.get("body", "")[:200],
                        "source": item.get("source", "Unknown"),
                        "published": datetime.fromtimestamp(
                            item.get("published_on", 0)
                        ).isoformat(),
                        "categories": item.get("categories", ""),
                        "tags": item.get("tags", ""),
                    })
                self._set_cache("cryptocompare", result)
                return result
        except Exception as e:
            logger.debug(f"CryptoCompare error: {e}")
        return []

    # ─── Composite: All News ─────────────────────

    def get_all_news(self, symbol: str = "") -> str:
        """
        Get all relevant news as formatted string for AI analysis.
        Combines multiple sources, deduplicates by title similarity.
        """
        all_articles = []

        # CryptoCompare (always free, no key)
        cc_news = self.get_cryptocompare_news()
        all_articles.extend(cc_news)

        # Finnhub
        fh_news = self.get_finnhub_news()
        all_articles.extend(fh_news)

        # NewsAPI (specific to symbol if given)
        if self.newsapi_key:
            query = f"crypto {symbol.split('/')[0]}" if symbol else "cryptocurrency"
            na_news = self.get_crypto_news(query, max_results=5)
            all_articles.extend(na_news)

        if not all_articles:
            return "No recent news available."

        # Deduplicate by title similarity
        seen_titles = set()
        unique = []
        for a in all_articles:
            title_key = a["title"].lower()[:40]
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique.append(a)

        # Format for AI
        lines = []
        for i, a in enumerate(unique[:10], 1):
            source = a.get("source", "")
            title = a.get("title", "")
            lines.append(f"  [{i}] ({source}) {title}")

        return "\n".join(lines)

    def check_breaking_news(self, keywords: List[str] = None) -> List[Dict]:
        """
        Check for breaking/high-impact news matching keywords.
        Keywords: ["trump", "fed", "hack", "ban", "crash", "war", "regulation"]
        """
        if keywords is None:
            keywords = [
                "trump", "fed", "rate", "hack", "exploit",
                "ban", "regulation", "crash", "war", "sanctions",
                "sec", "etf", "blackrock", "tether", "usdt",
                "delisting", "bankruptcy", "fraud",
            ]

        breaking = []

        # Check CryptoCompare (free, fast)
        news = self.get_cryptocompare_news()
        for article in news:
            title_lower = article["title"].lower()
            desc_lower = article.get("description", "").lower()
            combined = title_lower + " " + desc_lower

            for kw in keywords:
                if kw in combined:
                    article["matched_keyword"] = kw
                    breaking.append(article)
                    break

        return breaking[:5]
