"""
Trending Tracker — Real-Time Crypto Trending Detection
========================================================
Monitors for trending cryptocurrencies:
1. Volume spikes (unusual trading activity)
2. Price momentum (top gainers/losers)

Alerts when significant trending detected.
"""

import os
import time
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("trending_tracker")


class TrendingTracker:
    """Real-time trending cryptocurrency detection."""

    def __init__(self):
        self.scan_interval = int(os.getenv("TRENDING_SCAN_INTERVAL_MINUTES", "15"))
        self.volume_spike_threshold = 3.0
        self.price_change_threshold = 5.0
        
        self.last_scan = None
        self.trending_cache = []
        self.volume_history = {}

    def scan_trending(self) -> List[Dict]:
        """Full trending scan."""
        logger.info("🔍 Scanning for trending coins...")
        
        trending = []
        
        # Scan 1: Volume spikes
        volume_trending = self._scan_volume_spikes()
        trending.extend(volume_trending)
        
        # Scan 2: Price momentum
        momentum_trending = self._scan_price_momentum()
        trending.extend(momentum_trending)
        
        # Aggregate and score
        trending = self._aggregate_and_score(trending)
        
        self.last_scan = datetime.now()
        self.trending_cache = trending[:10]
        
        if trending:
            logger.info(f"🔥 Found {len(trending)} trending coins")
            for t in trending[:5]:
                logger.info(f"  {t['symbol']}: score={t['final_score']:.1f} ({t['sources']})")
        else:
            logger.info("No significant trending detected")
        
        return self.trending_cache

    def _scan_volume_spikes(self) -> List[Dict]:
        """Detect coins with unusual volume."""
        trending = []
        
        try:
            url = "https://api.coingecko.com/api/v3/coins/markets"
            params = {
                "vs_currency": "usd",
                "order": "volume_desc",
                "per_page": 100,
            }
            resp = requests.get(url, params=params, timeout=10)
            
            if resp.status_code != 200:
                return []
            
            data = resp.json()
            
            for coin in data:
                symbol = coin.get("symbol", "").upper()
                volume = coin.get("total_volume", 0) or 0
                market_cap = coin.get("market_cap", 0) or 0
                
                if volume < 10_000_000 or market_cap < 50_000_000:
                    continue
                
                vol_ratio = volume / market_cap if market_cap > 0 else 0
                avg_vol_ratio = self.volume_history.get(symbol, {}).get("avg_ratio", vol_ratio)
                
                # Spike detection
                if vol_ratio > avg_vol_ratio * self.volume_spike_threshold:
                    trending.append({
                        "symbol": symbol,
                        "name": coin.get("name", ""),
                        "price": coin.get("current_price", 0),
                        "volume_24h": volume,
                        "market_cap": market_cap,
                        "vol_ratio": vol_ratio,
                        "source": "volume_spike",
                        "trend_score": min(10, vol_ratio / avg_vol_ratio * 3) if avg_vol_ratio > 0 else 5,
                    })
                
                # Update history
                if symbol not in self.volume_history:
                    self.volume_history[symbol] = {"avg_ratio": vol_ratio, "count": 1}
                else:
                    hist = self.volume_history[symbol]
                    hist["avg_ratio"] = (hist["avg_ratio"] * hist["count"] + vol_ratio) / (hist["count"] + 1)
                    hist["count"] = min(hist["count"] + 1, 10)
        
        except Exception as e:
            logger.error(f"Volume scan error: {e}")
        
        return trending

    def _scan_price_momentum(self) -> List[Dict]:
        """Detect coins with strong price momentum."""
        trending = []
        
        try:
            url = "https://api.coingecko.com/api/v3/coins/markets"
            params = {
                "vs_currency": "usd",
                "order": "volume_desc",
                "per_page": 250,
                "price_change_percentage": "24h",
            }
            resp = requests.get(url, params=params, timeout=10)
            
            if resp.status_code != 200:
                return []
            
            data = resp.json()
            
            for coin in data:
                price_change_24h = coin.get("price_change_percentage_24h", 0) or 0
                volume = coin.get("total_volume", 0) or 0
                
                if abs(price_change_24h) >= self.price_change_threshold and volume > 5_000_000:
                    trending.append({
                        "symbol": coin.get("symbol", "").upper(),
                        "name": coin.get("name", ""),
                        "price": coin.get("current_price", 0),
                        "price_change_24h": price_change_24h,
                        "volume_24h": volume,
                        "market_cap": coin.get("market_cap", 0),
                        "source": "price_momentum",
                        "trend_score": min(10, abs(price_change_24h) / 2),
                    })
        
        except Exception as e:
            logger.error(f"Momentum scan error: {e}")
        
        return trending

    def _aggregate_and_score(self, trending: List[Dict]) -> List[Dict]:
        """Aggregate and calculate final score."""
        by_symbol = {}
        
        for t in trending:
            symbol = t["symbol"]
            if symbol not in by_symbol:
                by_symbol[symbol] = {
                    "symbol": symbol,
                    "name": t.get("name", symbol),
                    "price": t.get("price", 0),
                    "sources": [],
                    "trend_scores": [],
                }
            by_symbol[symbol]["sources"].append(t["source"])
            by_symbol[symbol]["trend_scores"].append(t["trend_score"])
        
        result = []
        for symbol, data in by_symbol.items():
            avg_score = sum(data["trend_scores"]) / len(data["trend_scores"])
            source_bonus = len(data["sources"]) * 0.5
            final_score = min(10, avg_score + source_bonus)
            
            data["final_score"] = final_score
            data["source_count"] = len(data["sources"])
            data["sources"] = ", ".join(set(data["sources"]))
            
            result.append(data)
        
        result.sort(key=lambda x: x["final_score"], reverse=True)
        return result

    def get_trending_coins(self, limit: int = 10) -> List[Dict]:
        """Get current trending coins."""
        return self.trending_cache[:limit]

    def is_trending(self, symbol: str) -> bool:
        """Check if a coin is trending."""
        return any(t["symbol"] == symbol.upper() for t in self.trending_cache)

    def get_status(self) -> Dict:
        """Get tracker status."""
        return {
            "last_scan": self.last_scan.isoformat() if self.last_scan else None,
            "trending_count": len(self.trending_cache),
            "scan_interval_min": self.scan_interval,
        }
