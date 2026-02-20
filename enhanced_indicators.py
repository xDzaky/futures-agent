
import os
import time
import requests
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("futures_agent")

class EnhancedIndicators:
    """
    Advanced Leading Indicators for Futures Trading.
    Uses Social Sentiment, On-Chain Metrics, and Macro Data to filter trades.
    """

    def __init__(self):
        # API Keys
        self.lunarcrush_key = os.getenv("LUNARCRUSH_API_KEY", "")
        self.santiment_key = os.getenv("SANTIMENT_API_KEY", "")
        self.fred_key = os.getenv("FRED_Economic_Data_API_KEY", "")
        self.etherscan_key = os.getenv("Etherscan_API_KEY", "")
        self.solscan_key = os.getenv("Solscan_API_KEY", "")
        
        self.session = requests.Session()
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes default

    def _cached(self, key, ttl=None):
        if key in self.cache:
            entry = self.cache[key]
            actual_ttl = ttl if ttl else self.cache_ttl
            if time.time() - entry["timestamp"] < actual_ttl:
                return entry["data"]
        return None

    def _set_cache(self, key, data):
        self.cache[key] = {
            "timestamp": time.time(),
            "data": data
        }

    def get_social_sentiment(self, symbol="BTC"):
        """
        LunarCrush: Get Social Dominance & Galaxy Score.
        Leading indicator for price reversals.
        
        Returns:
            dict: {sentiment_score: 1-100, social_volume: int, outlook: 'BULLISH'|'BEARISH'}
        """
        symbol = symbol.replace("USDT", "")
        cache_key = f"lunar_{symbol}"
        cached = self._cached(cache_key)
        if cached: return cached

        try:
            # LunarCrush V4 API
            url = f"https://lunarcrush.com/api4/public/coins/{symbol}/v1"
            headers = {"Authorization": f"Bearer {self.lunarcrush_key}"}
            
            resp = self.session.get(url, headers=headers, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                coin_data = data.get("data", {})
                
                galaxy_score = coin_data.get("galaxy_score", 50)
                alt_rank = coin_data.get("alt_rank", 100)
                sentiment_score = coin_data.get("sentiment", 50) # Assuming normalized 0-100
                
                outlook = "NEUTRAL"
                if galaxy_score > 75 or alt_rank < 10:
                    outlook = "BULLISH"
                elif galaxy_score < 40:
                    outlook = "BEARISH"
                
                result = {
                    "source": "LunarCrush",
                    "galaxy_score": galaxy_score,
                    "alt_rank": alt_rank,
                    "sentiment_score": sentiment_score,
                    "outlook": outlook
                }
                self._set_cache(cache_key, result)
                return result
            
        except Exception as e:
            logger.error(f"LunarCrush Error: {e}")
        
        return {"source": "LunarCrush", "error": "Failed to fetch"}

    def get_on_chain_metrics(self, symbol="bitcoin"):
        """
        Santiment: Get MVRV & Active Addresses.
        Fundamental indicator for overbought/oversold conditions.
        """
        # Map common symbols to slugs
        slug_map = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binance-coin", "XRP": "xrp"}
        slug = slug_map.get(symbol.replace("USDT", ""), "bitcoin")
        
        cache_key = f"san_{slug}"
        cached = self._cached(cache_key, ttl=3600) # 1 hour cache
        if cached: return cached

        try:
            query = """
            {
              getMetric(metric: "daily_active_addresses") {
                timeseriesData(
                  slug: "%s"
                  from: "utc_now-2d"
                  to: "utc_now"
                  interval: "1d"
                ) {
                  datetime
                  value
                }
              }
            }
            """ % slug
            
            url = "https://api.santiment.net/graphql"
            headers = {
                "Authorization": f"Apikey {self.santiment_key}",
                "Content-Type": "application/graphql"
            }
            
            resp = self.session.post(url, data=query, headers=headers, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                ts_data = data.get("data", {}).get("getMetric", {}).get("timeseriesData", [])
                
                active_addresses = 0
                trend = "STABLE"
                
                if len(ts_data) >= 2:
                    curr = ts_data[-1]["value"]
                    prev = ts_data[-2]["value"]
                    active_addresses = curr
                    if curr > prev * 1.05: trend = "RISING (Bullish)"
                    elif curr < prev * 0.95: trend = "FALLING (Bearish)"
                
                result = {
                    "source": "Santiment",
                    "metric": "daily_active_addresses",
                    "value": active_addresses,
                    "trend": trend
                }
                self._set_cache(cache_key, result)
                return result
                
        except Exception as e:
            logger.error(f"Santiment Error: {e}")
            
        return {"source": "Santiment", "error": "Failed to fetch"}

    def get_macro_risk(self):
        """
        FRED: Check VIX (Volatility) or Treasury Yields.
        If Risk is HIGH, reduce leverage or pause trading.
        """
        cache_key = "macro_risk"
        cached = self._cached(cache_key, ttl=14400) # 4 hours
        if cached: return cached
        
        try:
            # Series: T10Y2Y (10-Year Minus 2-Year Treasury Yield Spread) - Recession Indicator
            # Series: VIXCLS (CBOE Volatility Index)
            series_id = "VIXCLS" 
            url = "https://api.stlouisfed.org/fred/series/observations"
            params = {
                "series_id": series_id,
                "api_key": self.fred_key,
                "file_type": "json",
                "limit": 1,
                "sort_order": "desc"
            }
            
            resp = self.session.get(url, params=params, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                obs = data.get("observations", [])
                if obs:
                    vix_val = float(obs[0]["value"])
                    
                    risk_level = "LOW"
                    if vix_val > 20: risk_level = "MEDIUM"
                    if vix_val > 30: risk_level = "HIGH (CRASH WARNING)"
                    
                    result = {
                        "source": "FRED",
                        "indicator": "VIX",
                        "value": vix_val,
                        "risk_level": risk_level
                    }
                    self._set_cache(cache_key, result)
                    return result
                    
        except Exception as e:
            logger.error(f"FRED Error: {e}")
            
        return {"source": "FRED", "error": "Failed to fetch"}

    def get_combined_signal(self, symbol="BTC"):
        """
        Aggregates all indicators into a single trading bias.
        Returns: {bias: 'LONG'|'SHORT'|'NEUTRAL', confidence: float}
        """
        social = self.get_social_sentiment(symbol)
        onchain = self.get_on_chain_metrics(symbol)
        macro = self.get_macro_risk()
        
        score = 0
        factors = []
        
        # Social Logic
        if social.get("outlook") == "BULLISH":
            score += 1
            factors.append("Social Hype High")
        elif social.get("outlook") == "BEARISH":
            score -= 1
            factors.append("Social Sentiment Weak")
            
        # On-Chain Logic
        if onchain.get("trend") == "RISING (Bullish)":
            score += 1
            factors.append("Address Activity Rising")
        elif onchain.get("trend") == "FALLING (Bearish)":
            score -= 1
            factors.append("Address Activity Falling")
            
        # Macro Logic (Veto)
        if macro.get("risk_level") == "HIGH (CRASH WARNING)":
            score -= 2 # Strong penalty
            factors.append("Macro Risk HIGH")
            
        bias = "NEUTRAL"
        if score >= 1: bias = "LONG"
        if score <= -1: bias = "SHORT"
        
        return {
            "bias": bias,
            "net_score": score,
            "factors": factors,
            "details": {
                "social": social,
                "onchain": onchain,
                "macro": macro
            }
        }
