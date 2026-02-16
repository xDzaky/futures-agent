"""
Market Data — Real-Time & Historical Price Data
==================================================
Collects data from multiple free sources:
- Gate.io (primary — free, no geo-blocks)
- CryptoCompare (secondary — free, rate-limited)
- Binance API (fallback — may be blocked in some regions)
- CoinGecko (sentiment, trending, prices)
- Fear & Greed Index
"""

import os
import time
import logging
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger("market_data")

# CoinGecko ID map for common symbols
_CG_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
    "BNB": "binancecoin", "XRP": "ripple", "DOGE": "dogecoin",
    "ADA": "cardano", "AVAX": "avalanche-2", "DOT": "polkadot",
    "MATIC": "matic-network", "LINK": "chainlink", "LTC": "litecoin",
}


class MarketData:
    """Aggregates market data from multiple free sources."""

    def __init__(self, exchange=None):
        self.exchange = exchange
        self._cache = {}
        self._cache_ttl = {}
        self._binance_ok = None  # None = untested, True/False = tested

    def _cached(self, key: str, ttl: int = 30):
        if key in self._cache and key in self._cache_ttl:
            if time.time() - self._cache_ttl[key] < ttl:
                return self._cache[key]
        return None

    def _set_cache(self, key: str, data):
        self._cache[key] = data
        self._cache_ttl[key] = time.time()

    def _is_binance_reachable(self) -> bool:
        """Test Binance connectivity once, cache result for 5 min."""
        if self._binance_ok is not None:
            cached = self._cached("_binance_check", ttl=300)
            if cached is not None:
                return self._binance_ok
        try:
            resp = requests.get(
                "https://fapi.binance.com/fapi/v1/ping", timeout=3
            )
            self._binance_ok = resp.status_code == 200
        except Exception:
            self._binance_ok = False
        self._set_cache("_binance_check", self._binance_ok)
        return self._binance_ok

    # ─── Price Data ───────────────────────────────

    def get_candles(self, symbol: str, timeframe: str = "5m",
                    limit: int = 100) -> pd.DataFrame:
        """Get OHLCV candles as DataFrame."""
        cache_key = f"candles_{symbol}_{timeframe}_{limit}"
        cached = self._cached(cache_key, ttl=20)
        if cached is not None:
            return cached

        # Try exchange connector first
        if self.exchange:
            try:
                raw = self.exchange.get_ohlcv(symbol, timeframe, limit)
                if raw:
                    df = self._raw_to_df(raw, unit="ms")
                    if not df.empty:
                        self._set_cache(cache_key, df)
                        return df
            except Exception:
                pass

        # Primary: Gate.io (free, no rate limit issues)
        df = self._candles_gateio(symbol, timeframe, limit)
        if not df.empty:
            self._set_cache(cache_key, df)
            return df

        # Secondary: CryptoCompare (may hit rate limits)
        df = self._candles_cryptocompare(symbol, timeframe, limit)
        if not df.empty:
            self._set_cache(cache_key, df)
            return df

        # Fallback: Binance (if reachable)
        if self._is_binance_reachable():
            df = self._candles_binance(symbol, timeframe, limit)
            if not df.empty:
                self._set_cache(cache_key, df)
                return df

        return pd.DataFrame()

    def _candles_gateio(self, symbol: str, timeframe: str,
                        limit: int) -> pd.DataFrame:
        """Fetch candles from Gate.io (free, generous rate limits)."""
        # Gate.io format: BTC_USDT
        pair = symbol.replace("/", "_").split(":")[0]
        try:
            url = "https://api.gateio.ws/api/v4/spot/candlesticks"
            params = {"currency_pair": pair, "interval": timeframe, "limit": limit}
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                return pd.DataFrame()
            data = resp.json()
            if not data:
                return pd.DataFrame()

            # Gate.io format: [timestamp, volume_quote, close, high, low, open, volume_base, is_closed]
            rows = []
            for c in data:
                rows.append([
                    int(c[0]),     # unix timestamp (seconds)
                    float(c[5]),   # open
                    float(c[3]),   # high
                    float(c[4]),   # low
                    float(c[2]),   # close
                    float(c[6]),   # volume (base)
                ])
            df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
            df = df.sort_values("timestamp").reset_index(drop=True)
            df = df[df["close"] > 0].copy()
            return df
        except Exception as e:
            logger.debug(f"Gate.io candles error: {e}")
        return pd.DataFrame()

    def _candles_binance(self, symbol: str, timeframe: str,
                         limit: int) -> pd.DataFrame:
        pair = symbol.replace("/", "").replace(":USDT", "")
        try:
            url = "https://fapi.binance.com/fapi/v1/klines"
            params = {"symbol": pair, "interval": timeframe, "limit": limit}
            resp = requests.get(url, params=params, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                raw = [[c[0], c[1], c[2], c[3], c[4], c[5]] for c in data]
                return self._raw_to_df(raw, unit="ms")
        except Exception:
            pass
        return pd.DataFrame()

    def _candles_cryptocompare(self, symbol: str, timeframe: str,
                                limit: int) -> pd.DataFrame:
        """Fetch candles from CryptoCompare (free, always available)."""
        coin = symbol.split("/")[0]
        quote = symbol.split("/")[1] if "/" in symbol else "USDT"
        tf_min = self._tf_to_minutes(timeframe)

        # CryptoCompare only has histominute and histohour
        if tf_min < 60:
            endpoint = "histominute"
            raw_limit = limit * tf_min  # Need more 1m bars to resample
        else:
            endpoint = "histohour"
            raw_limit = limit * (tf_min // 60) if tf_min > 60 else limit

        raw_limit = min(raw_limit, 2000)
        url = f"https://min-api.cryptocompare.com/data/v2/{endpoint}"
        params = {"fsym": coin, "tsym": quote, "limit": raw_limit}

        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                return pd.DataFrame()
            data = resp.json().get("Data", {}).get("Data", [])
            if not data:
                return pd.DataFrame()

            df = pd.DataFrame(data)
            df["timestamp"] = pd.to_datetime(df["time"], unit="s")
            df = df.rename(columns={"volumefrom": "volume"})
            df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)
            df = df[df["close"] > 0].copy()

            # Resample if needed (e.g., 1m → 5m, 1h → 4h)
            if tf_min < 60 and tf_min > 1:
                df = df.set_index("timestamp").resample(f"{tf_min}min").agg({
                    "open": "first", "high": "max", "low": "min",
                    "close": "last", "volume": "sum",
                }).dropna().reset_index()
            elif tf_min > 60:
                hours = tf_min // 60
                df = df.set_index("timestamp").resample(f"{hours}h").agg({
                    "open": "first", "high": "max", "low": "min",
                    "close": "last", "volume": "sum",
                }).dropna().reset_index()

            # Trim to requested limit
            if len(df) > limit:
                df = df.tail(limit).reset_index(drop=True)

            return df
        except Exception as e:
            logger.debug(f"CryptoCompare candles error: {e}")
        return pd.DataFrame()

    def _raw_to_df(self, raw: list, unit: str = "ms") -> pd.DataFrame:
        if not raw:
            return pd.DataFrame()
        df = pd.DataFrame(raw, columns=[
            "timestamp", "open", "high", "low", "close", "volume"
        ])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit=unit)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        return df

    def _tf_to_minutes(self, tf: str) -> int:
        multipliers = {"m": 1, "h": 60, "d": 1440}
        unit = tf[-1]
        val = int(tf[:-1])
        return val * multipliers.get(unit, 1)

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        cache_key = f"price_{symbol}"
        cached = self._cached(cache_key, ttl=10)
        if cached is not None:
            return cached

        # Try exchange
        if self.exchange:
            try:
                ticker = self.exchange.get_ticker(symbol)
                if ticker and ticker.get("last"):
                    self._set_cache(cache_key, ticker["last"])
                    return ticker["last"]
            except Exception:
                pass

        # Try CoinGecko (fast, reliable)
        coin = symbol.split("/")[0]
        cg_id = _CG_IDS.get(coin)
        if cg_id:
            try:
                url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    price = resp.json().get(cg_id, {}).get("usd")
                    if price:
                        self._set_cache(cache_key, float(price))
                        return float(price)
            except Exception:
                pass

        # Try Gate.io
        pair = symbol.replace("/", "_").split(":")[0]
        try:
            url = f"https://api.gateio.ws/api/v4/spot/tickers?currency_pair={pair}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data and len(data) > 0:
                    price = float(data[0]["last"])
                    if price > 0:
                        self._set_cache(cache_key, price)
                        return price
        except Exception:
            pass

        # Try CryptoCompare
        try:
            url = f"https://min-api.cryptocompare.com/data/price?fsym={coin}&tsyms=USDT,USD"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                price = data.get("USDT") or data.get("USD")
                if price:
                    self._set_cache(cache_key, float(price))
                    return float(price)
        except Exception:
            pass

        # Last resort: Binance
        if self._is_binance_reachable():
            pair = symbol.replace("/", "").replace(":USDT", "")
            try:
                url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={pair}"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    price = float(resp.json()["price"])
                    self._set_cache(cache_key, price)
                    return price
            except Exception:
                pass

        return None

    def get_multi_timeframe(self, symbol: str) -> Dict[str, pd.DataFrame]:
        """Get candles for multiple timeframes."""
        timeframes = {"5m": 100, "15m": 96, "1h": 72, "4h": 48}
        result = {}
        for tf, limit in timeframes.items():
            df = self.get_candles(symbol, tf, limit)
            if not df.empty and len(df) >= 30:
                result[tf] = df
            time.sleep(0.3)  # Rate limit
        return result

    # ─── Orderbook ────────────────────────────────

    def get_orderbook_imbalance(self, symbol: str) -> Dict:
        """Analyze orderbook for buy/sell pressure."""
        default = {
            "imbalance": 0, "bid_volume": 0, "ask_volume": 0,
            "spread": 0, "signal": "NEUTRAL",
        }

        if self.exchange:
            try:
                ob = self.exchange.get_orderbook(symbol, 20)
                if ob:
                    return self._parse_orderbook(ob)
            except Exception:
                pass

        if self._is_binance_reachable():
            ob = self._fetch_binance_orderbook(symbol)
            if ob:
                return self._parse_orderbook(ob)

        return default

    def _parse_orderbook(self, ob: Dict) -> Dict:
        bids = ob.get("bids", [])
        asks = ob.get("asks", [])
        bid_vol = sum(b[1] for b in bids[:10])
        ask_vol = sum(a[1] for a in asks[:10])
        total = bid_vol + ask_vol
        imbalance = (bid_vol - ask_vol) / total if total > 0 else 0
        return {
            "imbalance": round(imbalance, 4),
            "bid_volume": round(bid_vol, 2),
            "ask_volume": round(ask_vol, 2),
            "spread": round(asks[0][0] - bids[0][0], 4) if bids and asks else 0,
            "signal": "BULLISH" if imbalance > 0.15 else (
                "BEARISH" if imbalance < -0.15 else "NEUTRAL"
            ),
        }

    def _fetch_binance_orderbook(self, symbol: str) -> Optional[Dict]:
        pair = symbol.replace("/", "").replace(":USDT", "")
        try:
            url = f"https://fapi.binance.com/fapi/v1/depth?symbol={pair}&limit=20"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "bids": [[float(b[0]), float(b[1])] for b in data["bids"]],
                    "asks": [[float(a[0]), float(a[1])] for a in data["asks"]],
                }
        except Exception:
            pass
        return None

    # ─── Funding Rate ─────────────────────────────

    def get_funding_rate(self, symbol: str) -> Dict:
        """Get funding rate (positive = longs pay shorts)."""
        if not self._is_binance_reachable():
            return {"rate": 0, "annualized": 0, "signal": "NEUTRAL"}

        pair = symbol.replace("/", "").replace(":USDT", "")
        try:
            url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={pair}&limit=1"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    rate = float(data[0]["fundingRate"])
                    return {
                        "rate": rate,
                        "annualized": round(rate * 3 * 365 * 100, 2),
                        "signal": "BEARISH" if rate > 0.001 else (
                            "BULLISH" if rate < -0.001 else "NEUTRAL"
                        ),
                    }
        except Exception:
            pass
        return {"rate": 0, "annualized": 0, "signal": "NEUTRAL"}

    # ─── Open Interest ────────────────────────────

    def get_open_interest(self, symbol: str) -> Dict:
        pair = symbol.replace("/", "").replace(":USDT", "")
        if not self._is_binance_reachable():
            return {"open_interest": 0, "symbol": pair}
        try:
            url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={pair}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return {"open_interest": float(data["openInterest"]), "symbol": pair}
        except Exception:
            pass
        return {"open_interest": 0, "symbol": pair}

    # ─── Fear & Greed ─────────────────────────────

    def get_fear_greed(self) -> Dict:
        cached = self._cached("fear_greed", ttl=300)
        if cached:
            return cached
        try:
            url = "https://api.alternative.me/fng/?limit=1"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()["data"][0]
                result = {
                    "value": int(data["value"]),
                    "classification": data["value_classification"],
                    "signal": "BULLISH" if int(data["value"]) > 60 else (
                        "BEARISH" if int(data["value"]) < 30 else "NEUTRAL"
                    ),
                }
                self._set_cache("fear_greed", result)
                return result
        except Exception:
            pass
        return {"value": 50, "classification": "Neutral", "signal": "NEUTRAL"}

    # ─── Composite Market Context ─────────────────

    def get_market_context(self, symbol: str) -> Dict:
        """Get full market context for AI analysis."""
        price = self.get_current_price(symbol)
        ob = self.get_orderbook_imbalance(symbol)
        funding = self.get_funding_rate(symbol)
        oi = self.get_open_interest(symbol)
        fg = self.get_fear_greed()

        return {
            "symbol": symbol,
            "price": price,
            "orderbook": ob,
            "funding": funding,
            "open_interest": oi,
            "fear_greed": fg,
            "timestamp": datetime.now().isoformat(),
        }
