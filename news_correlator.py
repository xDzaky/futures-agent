"""
Real-Time News Correlator using Tavily Search
==============================================
Searches for breaking news related to crypto trading pairs in real-time.
Uses Tavily API (1000 free searches/month) to find:
- Breaking news about specific tokens
- Market-moving events
- Regulatory news
- Exchange listings/delistings
- Major partnerships/hacks

Correlates news with trading signals to improve win rate.
"""

import os
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import time
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("news_correlator")


class NewsCorrelator:
    """Real-time news correlation using Tavily Search."""

    def __init__(self):
        self.tavily_key = os.getenv("TAVILY_API_KEY", "")
        self.enable_correlation = os.getenv("ENABLE_NEWS_CORRELATION", "true").lower() == "true"
        self.client = None
        self._cache = {}
        self._cache_ttl = {}
        self._last_search = 0
        self.total_searches = 0

        if self.tavily_key:
            try:
                # Dynamic import to avoid dependency if Tavily not used
                import importlib
                tavily = importlib.import_module("tavily")
                self.client = tavily.TavilyClient(api_key=self.tavily_key)
                logger.info("Tavily news correlator initialized")
            except ImportError:
                logger.warning("Tavily not installed. Run: pip install tavily-python")
            except Exception as e:
                logger.warning(f"Tavily init failed: {e}")

    def correlate_signal(self, signal: Dict) -> Dict:
        """
        Search for breaking news related to this signal and assess impact.

        Args:
            signal: {pair, side, confidence, ...}

        Returns:
            {
                "news_impact": "BULLISH/BEARISH/NEUTRAL",
                "confidence_adjustment": -0.3 to +0.3,
                "news_summary": "...",
                "sources": [...],
                "should_skip": bool
            }
        """
        if not self.enable_correlation or not self.client:
            return self._no_correlation()

        pair = signal.get("pair", "")
        side = signal.get("side", "")

        if not pair:
            return self._no_correlation()

        # Extract token symbol (e.g., BTC from BTC/USDT)
        token = pair.split("/")[0] if "/" in pair else pair
        token = token.replace("1000", "").replace("USDT", "")  # Clean up

        # Rate limit: max 1 search per 5 seconds (to avoid quota burnout)
        now = time.time()
        if now - self._last_search < 5:
            logger.debug(f"Rate limiting Tavily search for {token}")
            return self._no_correlation()

        # Check cache (5 min TTL)
        cache_key = f"news_{token}"
        cached = self._get_cache(cache_key, ttl=300)
        if cached:
            logger.debug(f"Using cached news for {token}")
            return cached

        logger.info(f"Searching breaking news for {token}...")

        try:
            # Search for recent news (last 24 hours) about this token
            query = f"{token} cryptocurrency news"

            response = self.client.search(
                query=query,
                search_depth="basic",
                max_results=5,
                include_domains=["cointelegraph.com", "coindesk.com", "bloomberg.com",
                                "reuters.com", "decrypt.co", "theblockcrypto.com"],
                days=1,  # Last 24 hours only
            )

            self._last_search = time.time()
            self.total_searches += 1

            results = response.get("results", [])

            if not results:
                logger.info(f"No recent news found for {token}")
                result = self._no_correlation()
                self._set_cache(cache_key, result)
                return result

            # Analyze news sentiment and relevance
            analysis = self._analyze_news(results, token, side)
            self._set_cache(cache_key, analysis)

            logger.info(f"News impact for {token}: {analysis['news_impact']} "
                       f"(adj: {analysis['confidence_adjustment']:+.2f})")

            return analysis

        except Exception as e:
            logger.error(f"Tavily search error: {e}")
            return self._no_correlation()

    def _analyze_news(self, results: List[Dict], token: str, trade_side: str) -> Dict:
        """Analyze news results and determine impact on signal."""
        # Collect headlines and snippets
        headlines = []
        sources = []

        for r in results[:5]:
            title = r.get("title", "")
            content = r.get("content", "")
            url = r.get("url", "")
            score = r.get("score", 0)

            if title:
                headlines.append(f"{title}: {content[:150]}")
                sources.append({"title": title, "url": url, "score": score})

        if not headlines:
            return self._no_correlation()

        # Simple sentiment analysis based on keywords
        combined_text = " ".join(headlines).lower()

        bullish_keywords = [
            "surge", "rally", "breakout", "adoption", "partnership", "listing",
            "bullish", "pump", "gains", "rise", "moon", "ath", "record high",
            "institutional", "etf approval", "integration", "upgrade", "launch"
        ]
        bearish_keywords = [
            "crash", "dump", "hack", "scam", "lawsuit", "ban", "regulation",
            "bearish", "decline", "fall", "drop", "sell-off", "sell off",
            "exploit", "bankruptcy", "delisting", "shutdown", "investigation"
        ]

        bullish_count = sum(1 for keyword in bullish_keywords if keyword in combined_text)
        bearish_count = sum(1 for keyword in bearish_keywords if keyword in combined_text)

        # Determine sentiment
        if bullish_count > bearish_count + 1:
            news_impact = "BULLISH"
            impact_strength = min(0.3, (bullish_count - bearish_count) * 0.1)
        elif bearish_count > bullish_count + 1:
            news_impact = "BEARISH"
            impact_strength = min(0.3, (bearish_count - bullish_count) * 0.1)
        else:
            news_impact = "NEUTRAL"
            impact_strength = 0.0

        # Check if news aligns with trade direction
        should_skip = False
        confidence_adjustment = 0.0

        if trade_side == "LONG":
            if news_impact == "BULLISH":
                # News supports LONG → boost confidence
                confidence_adjustment = +impact_strength
            elif news_impact == "BEARISH":
                # News contradicts LONG → reduce confidence or skip
                confidence_adjustment = -impact_strength
                if bearish_count >= 3:
                    should_skip = True
        elif trade_side == "SHORT":
            if news_impact == "BEARISH":
                # News supports SHORT → boost confidence
                confidence_adjustment = +impact_strength
            elif news_impact == "BULLISH":
                # News contradicts SHORT → reduce confidence or skip
                confidence_adjustment = -impact_strength
                if bullish_count >= 3:
                    should_skip = True

        summary = f"{len(results)} breaking news: {bullish_count} bullish, {bearish_count} bearish signals"

        return {
            "news_impact": news_impact,
            "confidence_adjustment": round(confidence_adjustment, 2),
            "news_summary": summary,
            "headlines": headlines[:3],
            "sources": sources,
            "should_skip": should_skip,
            "bullish_signals": bullish_count,
            "bearish_signals": bearish_count,
        }

    def _no_correlation(self) -> Dict:
        """Return neutral result when no news or correlation disabled."""
        return {
            "news_impact": "NEUTRAL",
            "confidence_adjustment": 0.0,
            "news_summary": "No breaking news detected",
            "sources": [],
            "should_skip": False,
        }

    def _get_cache(self, key: str, ttl: int = 300) -> Optional[Dict]:
        """Get cached result if not expired."""
        if key in self._cache and key in self._cache_ttl:
            if time.time() - self._cache_ttl[key] < ttl:
                return self._cache[key]
        return None

    def _set_cache(self, key: str, data: Dict):
        """Store result in cache."""
        self._cache[key] = data
        self._cache_ttl[key] = time.time()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    correlator = NewsCorrelator()

    # Test news correlation
    test_signals = [
        {"pair": "BTC/USDT", "side": "LONG", "confidence": 0.75},
        {"pair": "ETH/USDT", "side": "SHORT", "confidence": 0.70},
        {"pair": "SOL/USDT", "side": "LONG", "confidence": 0.65},
    ]

    for sig in test_signals:
        print(f"\n{'='*60}")
        print(f"Signal: {sig['side']} {sig['pair']} (conf={sig['confidence']})")
        result = correlator.correlate_signal(sig)
        print(f"News Impact: {result['news_impact']}")
        print(f"Confidence Adj: {result['confidence_adjustment']:+.2f}")
        print(f"Summary: {result['news_summary']}")
        print(f"Should Skip: {result['should_skip']}")
        if result.get("headlines"):
            print("Headlines:")
            for h in result["headlines"]:
                print(f"  - {h[:100]}...")
        time.sleep(6)  # Rate limit
