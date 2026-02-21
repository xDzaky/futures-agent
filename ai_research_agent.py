"""
AI Research Agent — Autonomous Crypto Research & Signal Generation
===================================================================
Actively searches for trading opportunities using:
1. Trending coins detection (volume spikes, gainers)
2. Real-time news search (Tavily API)
3. AI analysis & signal generation (Groq Llama 3.3 70B)

Runs every 5 minutes to find fresh opportunities.
"""

import os
import json
import time
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("ai_research")


class AIResearchAgent:
    """Autonomous AI researcher for crypto futures trading."""

    def __init__(self):
        # Groq Rotation
        self.groq_keys = [k.strip() for k in os.getenv("GROQ_API_KEYS", "").split(",") if k.strip()]
        if not self.groq_keys and os.getenv("GROQ_API_KEY"):
            self.groq_keys = [os.getenv("GROQ_API_KEY")]
        self.current_groq_idx = 0

        # Tavily Rotation
        self.tavily_keys = [k.strip() for k in os.getenv("TAVILY_API_KEYS", "").split(",") if k.strip()]
        if not self.tavily_keys and os.getenv("TAVILY_API_KEY"):
            self.tavily_keys = [os.getenv("TAVILY_API_KEY")]
        self.current_tavily_idx = 0
        
        self.cryptopanic_key = os.getenv("CRYPTOPANIC_API_KEY", "")
        
        self.enable_research = os.getenv("ENABLE_AI_RESEARCH", "true").lower() == "true"
        self.research_interval = int(os.getenv("RESEARCH_INTERVAL_MINUTES", "5"))
        self.max_searches_per_day = int(os.getenv("MAX_RESEARCH_SEARCHES_PER_DAY", "100")) # Boosted
        
        self._init_clients()
        
        # State
        self.searches_today = 0
        self.last_reset = datetime.now().date()
        self.last_research = None
        self.trending_coins = []
        self.last_trending_update = None

    def _init_clients(self):
        """Initialize clients for research."""
        g_key = self.groq_keys[self.current_groq_idx] if self.groq_keys else None
        if g_key:
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=g_key)
            except Exception as e:
                logger.warning(f"Groq init failed: {e}")
                self.groq_client = None
        else:
            self.groq_client = None

    def run_research_cycle(self) -> List[Dict]:
        """Run a full research cycle."""
        if not self.enable_research or not self.groq_client:
            return []
        
        # Reset daily counter
        if datetime.now().date() > self.last_reset:
            self.searches_today = 0
            self.last_reset = datetime.now().date()
        
        if self.searches_today >= self.max_searches_per_day:
            logger.warning(f"Daily research limit reached ({self.max_searches_per_day})")
            return []
        
        logger.info(f"🔬 Starting AI research cycle... (searches: {self.searches_today}/{self.max_searches_per_day})")
        
        signals = []
        trending = self._get_trending_coins()
        
        if not trending:
            return []
        
        logger.info(f"Found {len(trending)} trending coins")
        
        for coin_data in trending[:3]:  # Max 3 coins per cycle
            if self.searches_today >= self.max_searches_per_day:
                break
            
            coin = coin_data.get("symbol")
            if not coin:
                continue
            
            logger.info(f"Researching {coin}...")
            
            # Search news
            news_results = self._search_news(coin)
            
            # AI analysis & signal generation
            signal = self._analyze_and_generate_signal(coin, coin_data, news_results)
            
            if signal:
                signals.append(signal)
                logger.info(f"✅ Generated signal for {coin}: {signal.get('action')} (conf: {signal.get('confidence', 0):.0%})")
            
            self.searches_today += 1
            time.sleep(2)
        
        self.last_research = datetime.now()
        
        if signals:
            logger.info(f"🎯 Research cycle complete: {len(signals)} signals generated")
        else:
            logger.info("🎯 Research cycle complete: No high-confidence signals")
        
        return signals

    def _get_trending_coins(self) -> List[Dict]:
        """Get trending coins from CoinGecko."""
        cache_age = datetime.now() - self.last_trending_update if self.last_trending_update else timedelta(hours=1)
        
        if cache_age < timedelta(minutes=15) and self.trending_coins:
            return self.trending_coins
        
        trending = []
        
        try:
            url = "https://api.coingecko.com/api/v3/coins/markets"
            params = {
                "vs_currency": "usd",
                "order": "volume_desc",
                "per_page": 50,
                "price_change_percentage": "24h",
            }
            resp = requests.get(url, params=params, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                for coin in data[:20]:
                    price_change = coin.get("price_change_percentage_24h", 0) or 0
                    volume = coin.get("total_volume", 0) or 0
                    market_cap = coin.get("market_cap", 0) or 0
                    
                    # Filter: positive momentum + decent volume
                    if abs(price_change) > 3 and volume > 10_000_000 and market_cap > 100_000_000:
                        trending.append({
                            "symbol": coin.get("symbol", "").upper(),
                            "name": coin.get("name", ""),
                            "price": coin.get("current_price", 0),
                            "price_change_24h": price_change,
                            "volume_24h": volume,
                            "market_cap": market_cap,
                            "source": "coingecko_gainers",
                        })
        except Exception as e:
            logger.error(f"CoinGecko error: {e}")
        
        # Fallback
        if not trending:
            for symbol in ["BTC", "ETH", "SOL"]:
                trending.append({
                    "symbol": symbol,
                    "name": symbol,
                    "price": 0,
                    "price_change_24h": 0,
                    "volume_24h": 0,
                    "market_cap": 0,
                    "source": "fallback",
                })
        
        self.trending_coins = trending[:10]
        self.last_trending_update = datetime.now()
        
        return self.trending_coins

    def _search_news(self, symbol: str) -> List[Dict]:
        """Search latest news with Tavily Key Rotation."""
        if not self.tavily_keys: return []
        
        max_retries = len(self.tavily_keys)
        for attempt in range(max_retries):
            key = self.tavily_keys[self.current_tavily_idx]
            try:
                from tavily import TavilyClient
                client = TavilyClient(api_key=key)
                
                response = client.search(
                    query=f"{symbol} crypto news sentiment",
                    search_depth="advanced", # Quality over quantity
                    max_results=5,
                    days=1,
                )
                
                results = response.get("results", [])
                news = []
                for r in results:
                    news.append({"title": r.get("title", ""), "content": r.get("content", ""), "url": r.get("url", "")})
                
                return news
            except Exception as e:
                if "limit" in str(e).lower() and len(self.tavily_keys) > 1:
                    logger.warning(f"Tavily Key {self.current_tavily_idx} hit limit. Rotating...")
                    self.current_tavily_idx = (self.current_tavily_idx + 1) % len(self.tavily_keys)
                    continue
                logger.error(f"Tavily error: {e}")
                break
        return []

    def _analyze_and_generate_signal(self, symbol: str, coin_data: Dict, news: List[Dict]) -> Optional[Dict]:
        """AI analysis with Groq Key Rotation."""
        if not self.groq_client: return None
        
        max_retries = len(self.groq_keys)
        for attempt in range(max_retries):
            try:
                news_text = "\n".join([f"- {n['title']}" for n in news[:5]])
                prompt = f"Analyze {symbol} trade: {json.dumps(coin_data)}\nNews: {news_text}"
                
                response = self.groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.2
                )
                
                return json.loads(response.choices[0].message.content)
            except Exception as e:
                if "429" in str(e) and len(self.groq_keys) > 1:
                    logger.warning(f"Research Groq Key {self.current_groq_idx} limit. Rotating...")
                    self.current_groq_idx = (self.current_groq_idx + 1) % len(self.groq_keys)
                    self._init_clients()
                    continue
                logger.error(f"Research Groq error: {e}")
                break
        return None

    def get_research_status(self) -> Dict:
        """Get current research agent status."""
        return {
            "enabled": self.enable_research,
            "last_research": self.last_research.isoformat() if self.last_research else None,
            "searches_today": self.searches_today,
            "max_searches": self.max_searches_per_day,
            "trending_coins": [c["symbol"] for c in self.trending_coins[:5]],
        }

    def manual_research(self, symbol: str) -> Optional[Dict]:
        """Manual research for a specific coin."""
        logger.info(f"🔬 Manual research requested for {symbol}")
        
        coin_data = {
            "symbol": symbol.upper(),
            "name": symbol,
            "price": 0,
            "price_change_24h": 0,
            "volume_24h": 0,
            "market_cap": 0,
            "source": "manual",
        }
        
        news = self._search_news(symbol.upper())
        signal = self._analyze_and_generate_signal(symbol.upper(), coin_data, news)
        
        if signal:
            self.searches_today += 1
        
        return signal
