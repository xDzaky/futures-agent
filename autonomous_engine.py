"""
Autonomous Trading Engine
==========================
Self-contained engine that finds & executes high-probability trades
WITHOUT waiting for Telegram channel signals.

Strategy Stack (for maximum win rate):
1. Multi-Timeframe Trend Alignment (1h + 4h must agree)
2. Key Level Detection (support/resistance, swing highs/lows)
3. Entry Confirmation (candle pattern + volume surge)
4. Smart SL Placement (BELOW key level, not ATR flat multiply)
5. Dynamic Volatility Filter (avoid entries in choppy/ranging conditions)
6. Funding Rate Bias (avoid longs in extreme positive funding)
7. Fear & Greed Sentiment Gate
8. AI Final Confirmation (Groq analyzes full setup)

Win Rate Target: >60% by only trading HIGH-CONFLUENCE setups
"""

import os
import json
import logging
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from market_data import MarketData
from technical import TechnicalAnalyzer, ema, rsi, macd, bollinger_bands, atr, stoch_rsi

logger = logging.getLogger("autonomous")


# ─── Pairs to scan autonomously (50 high-volume pairs) ──────
AUTONOMOUS_PAIRS = [
    # Mega caps (always scan)
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    # Large caps
    "AVAX/USDT", "LINK/USDT", "ADA/USDT", "DOT/USDT", "MATIC/USDT",
    "DOGE/USDT", "SUI/USDT", "TIA/USDT", "INJ/USDT", "FET/USDT",
    "WIF/USDT", "PEPE/USDT", "NEAR/USDT", "ATOM/USDT", "ARB/USDT",
    # Mid caps
    "OP/USDT", "APT/USDT", "RENDER/USDT", "HBAR/USDT", "LDO/USDT",
    "AAVE/USDT", "UNI/USDT", "ENA/USDT", "JUP/USDT", "WLD/USDT",
    "PENDLE/USDT", "PYTH/USDT", "JTO/USDT", "ETHFI/USDT", "IO/USDT",
    "BLUR/USDT", "DYDX/USDT", "ICP/USDT", "FIL/USDT", "RUNE/USDT",
    "COMP/USDT", "GRT/USDT", "SNX/USDT", "THETA/USDT", "VET/USDT",
    # Small/new caps (higher vol, from signal channels)
    "ENSO/USDT", "BIO/USDT", "MORPHO/USDT", "MOVE/USDT", "USUAL/USDT",
    "EIGEN/USDT", "STRK/USDT", "ALT/USDT", "PIXEL/USDT", "PORTAL/USDT",
]

# Minimum confluence score to take a trade (0-100)
MIN_CONFLUENCE_SCORE = 68  # Slightly relaxed from 72 to get more trades while still selective


class StructureAnalyzer:
    """
    Detects key price structure levels: swing highs/lows, support/resistance.
    Used for smart SL placement BELOW structure (not arbitrary ATR).
    """

    def find_swing_levels(self, df: pd.DataFrame, lookback: int = 20) -> Dict:
        """Find recent swing highs and lows with strength score."""
        if df is None or len(df) < lookback + 5:
            return {"swing_high": None, "swing_low": None, "highs": [], "lows": []}

        highs = []
        lows = []

        # Detect swing pivots (local max/min over N candles each side)
        n = 3  # N candles on each side to confirm pivot
        for i in range(n, len(df) - n):
            window_high = df["high"].iloc[i - n:i + n + 1]
            window_low = df["low"].iloc[i - n:i + n + 1]

            if df["high"].iloc[i] == window_high.max():
                # Swing high
                strength = (df["high"].iloc[i] - window_high.min()) / window_high.min() * 100
                highs.append({
                    "price": float(df["high"].iloc[i]),
                    "index": i,
                    "strength": round(float(strength), 3),
                    "age": len(df) - i,  # candles ago
                })

            if df["low"].iloc[i] == window_low.min():
                # Swing low
                strength = (window_low.max() - df["low"].iloc[i]) / df["low"].iloc[i] * 100
                lows.append({
                    "price": float(df["low"].iloc[i]),
                    "index": i,
                    "strength": round(float(strength), 3),
                    "age": len(df) - i,
                })

        # Sort by recency (most recent first)
        highs.sort(key=lambda x: x["age"])
        lows.sort(key=lambda x: x["age"])

        # Most recent significant levels (last 30 candles)
        recent_highs = [h for h in highs if h["age"] <= lookback]
        recent_lows = [l for l in lows if l["age"] <= lookback]

        return {
            "swing_high": recent_highs[0]["price"] if recent_highs else None,
            "swing_low": recent_lows[0]["price"] if recent_lows else None,
            "highs": recent_highs[:5],
            "lows": recent_lows[:5],
        }

    def find_support_resistance(self, df: pd.DataFrame, zone_pct: float = 0.5) -> Dict:
        """
        Find support/resistance zones using price clustering.
        Groups nearby swing levels into zones.
        """
        if df is None or len(df) < 50:
            return {"supports": [], "resistances": []}

        price = float(df["close"].iloc[-1])
        swing_data = self.find_swing_levels(df, lookback=50)

        # All levels above current price = resistance, below = support
        all_levels = (
            [(h["price"], h["strength"]) for h in swing_data["highs"]] +
            [(l["price"], l["strength"]) for l in swing_data["lows"]]
        )

        supports = [(p, s) for p, s in all_levels if p < price * 0.998]
        resistances = [(p, s) for p, s in all_levels if p > price * 1.002]

        supports.sort(key=lambda x: x[0], reverse=True)  # Nearest first
        resistances.sort(key=lambda x: x[0])  # Nearest first

        return {
            "nearest_support": supports[0][0] if supports else None,
            "nearest_resistance": resistances[0][0] if resistances else None,
            "supports": supports[:3],
            "resistances": resistances[:3],
        }

    def smart_sl_placement(self, df: pd.DataFrame, side: str, entry_price: float,
                           atr_val: float) -> Tuple[float, str]:
        """
        Place SL at key structural level rather than flat ATR multiply.
        This is the key insight for reducing SL hits.

        Rules:
        - LONG: SL just BELOW the nearest swing low (gives room)
        - SHORT: SL just ABOVE the nearest swing high
        - Fallback: 1.5x ATR if no level found
        - Safety cap: SL never more than 4% from entry

        Returns (sl_price, method_used)
        """
        structure = self.find_swing_levels(df, lookback=30)
        atr_sl = atr_val * 1.5
        max_sl_pct = 0.04  # 4% max

        if side == "LONG":
            # Look for swing low below entry as natural SL level
            candidate_sl = None
            for low in structure["lows"]:
                lp = low["price"]
                # Must be below entry, not too far
                distance_pct = (entry_price - lp) / entry_price
                if lp < entry_price * 0.998 and distance_pct <= max_sl_pct:
                    candidate_sl = lp * 0.998  # Slight buffer below the level
                    break

            if candidate_sl:
                return round(candidate_sl, 6), "structure_low"
            else:
                # Fallback to ATR
                sl = entry_price - min(atr_sl, entry_price * max_sl_pct)
                return round(sl, 6), "atr_fallback"

        else:  # SHORT
            candidate_sl = None
            for high in structure["highs"]:
                hp = high["price"]
                distance_pct = (hp - entry_price) / entry_price
                if hp > entry_price * 1.002 and distance_pct <= max_sl_pct:
                    candidate_sl = hp * 1.002  # Slight buffer above the level
                    break

            if candidate_sl:
                return round(candidate_sl, 6), "structure_high"
            else:
                sl = entry_price + min(atr_sl, entry_price * max_sl_pct)
                return round(sl, 6), "atr_fallback"


class VolatilityFilter:
    """
    Prevents entries in choppy/ranging markets where SL rate is high.
    Only allows trades in trending/expanding volatility conditions.
    """

    def is_trending(self, df: pd.DataFrame) -> Tuple[bool, str]:
        """
        Check if market is trending rather than ranging.
        Uses ADX-like calculation and BB width.

        Returns (is_trending, reason)
        """
        if df is None or len(df) < 30:
            return False, "Insufficient data"

        close = df["close"]
        high = df["high"]
        low = df["low"]

        # BB Width (squeeze detection)
        bb = bollinger_bands(close, 20, 2)
        if bb.empty:
            return False, "No BB data"

        bb_width = (bb["upper"].iloc[-1] - bb["lower"].iloc[-1]) / bb["mid"].iloc[-1]
        bb_width_avg = ((bb["upper"] - bb["lower"]) / bb["mid"]).rolling(10).mean().iloc[-1]

        # Expanding BB = breakout / trend starting
        # Squeeze (narrow BB) = ranging = avoid
        bb_expanding = bb_width > bb_width_avg * 1.1

        # EMA slope (trend strength)
        ema_21 = ema(close, 21)
        ema_slope = (ema_21.iloc[-1] - ema_21.iloc[-5]) / ema_21.iloc[-5] * 100
        strong_slope = abs(ema_slope) > 0.3  # At least 0.3% slope over 5 bars

        # ATR ratio (volatility)
        atr_series = atr(high, low, close, 14)
        atr_now = atr_series.iloc[-1]
        atr_avg = atr_series.rolling(20).mean().iloc[-1]
        vol_ratio = atr_now / atr_avg if atr_avg > 0 else 1.0
        good_volatility = 0.7 < vol_ratio < 3.0  # Not too quiet, not too chaotic

        trending = (bb_expanding or strong_slope) and good_volatility

        reason = (
            f"BB={'expanding' if bb_expanding else 'squeeze'} "
            f"slope={ema_slope:.2f}% "
            f"vol_ratio={vol_ratio:.2f}"
        )
        return trending, reason

    def get_regime(self, df_1h: pd.DataFrame, df_4h: pd.DataFrame) -> str:
        """
        Determine market regime: TRENDING_UP / TRENDING_DOWN / RANGING
        Based on higher timeframe structure.
        """
        if df_1h is None or df_4h is None:
            return "UNKNOWN"

        # 4h EMA alignment
        ema_50_4h = ema(df_4h["close"], 50).iloc[-1]
        ema_21_4h = ema(df_4h["close"], 21).iloc[-1]
        price_4h = df_4h["close"].iloc[-1]

        if price_4h > ema_21_4h > ema_50_4h:
            return "TRENDING_UP"
        elif price_4h < ema_21_4h < ema_50_4h:
            return "TRENDING_DOWN"
        else:
            return "RANGING"


class EntryPatternDetector:
    """
    Detects high-probability entry candle patterns.
    Only entry on CONFIRMATION, not prediction.
    """

    def detect_bullish_patterns(self, df: pd.DataFrame) -> Dict:
        """Detect bullish entry patterns on last 3 candles."""
        if df is None or len(df) < 10:
            return {"found": False, "pattern": None, "strength": 0}

        patterns = []
        last = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]

        body_last = abs(last["close"] - last["open"])
        range_last = last["high"] - last["low"]
        body_prev = abs(prev["close"] - prev["open"])

        # --- Bullish Engulfing ---
        if (prev["close"] < prev["open"] and  # Previous bearish
                last["close"] > last["open"] and  # Current bullish
                last["close"] > prev["open"] and  # Body engulfs
                last["open"] < prev["close"]):
            patterns.append(("bullish_engulfing", 80))

        # --- Hammer / Pin Bar ---
        lower_wick = last["open"] - last["low"] if last["close"] > last["open"] else last["close"] - last["low"]
        if (lower_wick > body_last * 2.5 and  # Long lower wick
                body_last > 0 and
                last["close"] > last["open"]):  # Bullish close
            patterns.append(("hammer", 70))

        # --- Morning Star (3-candle) ---
        if (prev2["close"] < prev2["open"] and  # First bearish
                abs(prev["close"] - prev["open"]) < body_last * 0.5 and  # Doji in middle
                last["close"] > last["open"] and  # Third bullish
                last["close"] > (prev2["open"] + prev2["close"]) / 2):  # Closes above midpoint
            patterns.append(("morning_star", 85))

        # --- Strong bullish momentum (consecutive closes) ---
        if (last["close"] > last["open"] and
                prev["close"] > prev["open"] and
                last["close"] > prev["close"] and
                df["volume"].iloc[-1] > df["volume"].rolling(10).mean().iloc[-1] * 1.2):
            patterns.append(("momentum_surge", 65))

        if not patterns:
            return {"found": False, "pattern": None, "strength": 0}

        best = max(patterns, key=lambda x: x[1])
        return {"found": True, "pattern": best[0], "strength": best[1]}

    def detect_bearish_patterns(self, df: pd.DataFrame) -> Dict:
        """Detect bearish entry patterns on last 3 candles."""
        if df is None or len(df) < 10:
            return {"found": False, "pattern": None, "strength": 0}

        patterns = []
        last = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]

        body_last = abs(last["close"] - last["open"])

        # --- Bearish Engulfing ---
        if (prev["close"] > prev["open"] and
                last["close"] < last["open"] and
                last["close"] < prev["open"] and
                last["open"] > prev["close"]):
            patterns.append(("bearish_engulfing", 80))

        # --- Shooting Star ---
        upper_wick = last["high"] - last["close"] if last["close"] < last["open"] else last["high"] - last["open"]
        if (upper_wick > body_last * 2.5 and
                body_last > 0 and
                last["close"] < last["open"]):
            patterns.append(("shooting_star", 70))

        # --- Evening Star (3-candle) ---
        if (prev2["close"] > prev2["open"] and
                abs(prev["close"] - prev["open"]) < body_last * 0.5 and
                last["close"] < last["open"] and
                last["close"] < (prev2["open"] + prev2["close"]) / 2):
            patterns.append(("evening_star", 85))

        # --- Strong bearish momentum ---
        if (last["close"] < last["open"] and
                prev["close"] < prev["open"] and
                last["close"] < prev["close"] and
                df["volume"].iloc[-1] > df["volume"].rolling(10).mean().iloc[-1] * 1.2):
            patterns.append(("momentum_dump", 65))

        if not patterns:
            return {"found": False, "pattern": None, "strength": 0}

        best = max(patterns, key=lambda x: x[1])
        return {"found": True, "pattern": best[0], "strength": best[1]}


class AutonomousEngine:
    """
    Main engine: scans markets autonomously, finds high-win-rate setups,
    and executes them without waiting for Telegram signals.
    """

    def __init__(self, market: MarketData, db, tg_send_fn,
                 max_positions: int = 3,
                 min_confluence: int = MIN_CONFLUENCE_SCORE):

        self.market = market
        self.db = db
        self.tg_send = tg_send_fn
        self.max_positions = max_positions
        self.min_confluence = min_confluence

        # Sub-analyzers
        self.ta = TechnicalAnalyzer()
        self.structure = StructureAnalyzer()
        self.vol_filter = VolatilityFilter()
        self.pattern_detector = EntryPatternDetector()

        # AI for final confirmation
        self.groq_client = None
        groq_key = os.getenv("GROQ_API_KEY", "")
        if groq_key:
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=groq_key)
                logger.info("✓ Groq AI connected for autonomous confirmation")
            except Exception as e:
                logger.warning(f"Groq init failed: {e}")

        # Scan state
        self.last_scan: Dict[str, datetime] = {}  # pair → last scan time
        self.scan_cooldown = int(os.getenv("AUTONOMOUS_SCAN_COOLDOWN_MIN", "15"))  # min between scans per pair

        # Track scanned pairs for logging
        self.scan_count = 0
        self.setups_found = 0
        self.auto_trades = 0

        logger.info(
            f"✓ AutonomousEngine initialized | pairs={len(AUTONOMOUS_PAIRS)} "
            f"min_confluence={min_confluence} cooldown={self.scan_cooldown}min"
        )

    async def run_scan_loop(self, interval_minutes: int = 10):
        """Background loop: scan all pairs every N minutes."""
        logger.info(f"🤖 Autonomous scan loop started (interval={interval_minutes}min)")
        while True:
            try:
                await asyncio.sleep(interval_minutes * 60)
                await self.scan_all_pairs()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f"Autonomous scan error: {e}")
                await asyncio.sleep(60)

    async def scan_all_pairs(self) -> List[Dict]:
        """Scan all pairs and execute high-probability setups."""
        # Check position limit first
        open_trades = self.db.get_open_trades()
        if len(open_trades) >= self.max_positions:
            logger.info(f"🤖 AUTO SCAN: Max positions reached ({self.max_positions}), skipping")
            return []

        executed = []
        self.scan_count += 1
        logger.info(f"🤖 AUTO SCAN #{self.scan_count} — scanning {len(AUTONOMOUS_PAIRS)} pairs...")

        # Global market filter using Fear & Greed
        fg = self.market.get_fear_greed()
        fg_value = fg.get("value", 50)

        # In extreme conditions, restrict direction rather than skip entirely:
        # Extreme Fear (<= 15): Market is oversold → ONLY allow SHORT (ride the downtrend)
        # Extreme Greed (>= 90): Market is overbought → ONLY allow LONG cautiously
        # Normal (15-90): Allow both directions
        forced_direction = None
        if fg_value <= 15:
            forced_direction = "SHORT"  # Extreme fear = downtrend in progress, only short
            logger.info(f"🤖 EXTREME FEAR (F&G={fg_value}) — only scanning SHORT setups")
        elif fg_value >= 90:
            forced_direction = "LONG"   # Extreme greed = momentum up, only long
            logger.info(f"🤖 EXTREME GREED (F&G={fg_value}) — only scanning LONG setups")
        else:
            logger.info(f"🤖 F&G={fg_value} — scanning both directions")

        for pair in AUTONOMOUS_PAIRS:
            # Check cooldown per pair — use total_seconds() to handle >1h durations
            last_scan = self.last_scan.get(pair)
            if last_scan and (datetime.now() - last_scan).total_seconds() < self.scan_cooldown * 60:
                continue

            # Check if we already have this pair open
            open_symbols = [t["symbol"] for t in self.db.get_open_trades()]
            if pair in open_symbols:
                continue

            try:
                setup = await self._analyze_pair(pair, fg_value)
                self.last_scan[pair] = datetime.now()

                # Apply forced_direction filter (extreme market condition)
                if setup and forced_direction and setup.get("side") != forced_direction:
                    logger.debug(f"  {pair}: SKIP (forced {forced_direction}, setup is {setup['side']})")
                    setup = None

                if setup and setup.get("confluence_score", 0) >= self.min_confluence:
                    self.setups_found += 1
                    logger.info(
                        f"🎯 HIGH-PROB SETUP: {setup['side']} {pair} | "
                        f"confluence={setup['confluence_score']:.0f} | "
                        f"pattern={setup.get('pattern', 'N/A')}"
                    )

                    success = await self._execute_autonomous_trade(setup)
                    if success:
                        executed.append(setup)
                        self.auto_trades += 1

                        # Max 2 auto trades per scan cycle
                        if len(executed) >= 2:
                            break

            except Exception as e:
                logger.error(f"🤖 Error scanning {pair}: {e}")

            await asyncio.sleep(2)  # Rate limit between pairs

        if not executed:
            logger.info(f"🤖 AUTO SCAN #{self.scan_count} complete — no high-confluence setups found")

        return executed

    async def _analyze_pair(self, pair: str, fg_value: int = 50) -> Optional[Dict]:
        """
        Full multi-layer analysis of one pair.
        Returns setup dict if high-probability, else None.
        """
        # ── Step 1: Get multi-timeframe candles ───────────────────
        candles = {}
        for tf, limit in [("15m", 100), ("1h", 100), ("4h", 72)]:
            df = self.market.get_candles(pair, tf, limit)
            if not df.empty and len(df) >= 30:
                candles[tf] = df
            await asyncio.sleep(0.3)

        if len(candles) < 2:
            return None

        df_15m = candles.get("15m")
        df_1h = candles.get("1h")
        df_4h = candles.get("4h")

        if df_1h is None:
            return None

        price = float(df_1h["close"].iloc[-1])
        if price <= 0:
            return None

        # ── Step 2: Volatility / Regime Filter ───────────────────
        is_trending, trend_reason = self.vol_filter.is_trending(df_1h)
        if not is_trending:
            logger.debug(f"  {pair}: SKIP (ranging) — {trend_reason}")
            return None

        regime = self.vol_filter.get_regime(df_1h, df_4h) if df_4h is not None else "UNKNOWN"

        # ── Step 3: Multi-Timeframe TA ────────────────────────────
        ta_1h = self.ta.analyze(df_1h, "1h")
        ta_4h = self.ta.analyze(df_4h, "4h") if df_4h is not None else {"signal": "SKIP", "score": 50}
        ta_15m = self.ta.analyze(df_15m, "15m") if df_15m is not None else {"signal": "SKIP", "score": 50}

        score_1h = ta_1h.get("score", 50)
        score_4h = ta_4h.get("score", 50)
        score_15m = ta_15m.get("score", 50)
        sig_1h = ta_1h.get("signal", "SKIP")
        sig_4h = ta_4h.get("signal", "SKIP")

        # REQUIRE 1h AND 4h to align — this is the primary filter for win rate
        if sig_1h != sig_4h or sig_1h == "SKIP":
            logger.debug(f"  {pair}: SKIP (TF mismatch 1h={sig_1h} 4h={sig_4h})")
            return None

        direction = sig_1h  # LONG or SHORT

        # ── Step 4: ATR for SL calculation ───────────────────────
        atr_series = atr(df_1h["high"], df_1h["low"], df_1h["close"], 14)
        atr_val = float(atr_series.iloc[-1]) if not atr_series.empty else price * 0.01

        # ── Step 5: Structure-Based SL Placement ─────────────────
        sl_price, sl_method = self.structure.smart_sl_placement(df_1h, direction, price, atr_val)
        sl_dist_pct = abs(price - sl_price) / price * 100

        # Reject if SL too wide or too tight
        if sl_dist_pct > 3.5 or sl_dist_pct < 0.2:
            logger.debug(f"  {pair}: SKIP (SL dist {sl_dist_pct:.1f}% out of range 0.2-3.5%)")
            return None

        # ── Step 6: Entry Candle Pattern (15m or 1h) ─────────────
        entry_df = df_15m if df_15m is not None else df_1h
        if direction == "LONG":
            pattern = self.pattern_detector.detect_bullish_patterns(entry_df)
        else:
            pattern = self.pattern_detector.detect_bearish_patterns(entry_df)

        # ── Step 7: Volume Confirmation ───────────────────────────
        vol_ratio = ta_1h.get("volume_ratio", 1.0)
        vol_signal = ta_1h.get("volume_signal", "NORMAL")
        volume_confirms = vol_ratio >= 1.2  # At least 20% above average

        # ── Step 8: RSI Filter (avoid extreme zones on entry TF) ──
        rsi_val = ta_1h.get("rsi", 50)
        rsi_warn = (direction == "LONG" and rsi_val > 75) or (direction == "SHORT" and rsi_val < 25)
        if rsi_warn:
            logger.debug(f"  {pair}: SKIP (RSI={rsi_val:.0f} extreme on entry direction)")
            return None

        # ── Step 9: Funding Rate Filter ───────────────────────────
        funding = self.market.get_funding_rate(pair)
        funding_rate = funding.get("rate", 0)
        # Very high positive funding → crowded longs → avoid LONG
        # Very negative funding → crowded shorts → avoid SHORT
        if direction == "LONG" and funding_rate > 0.002:
            logger.debug(f"  {pair}: SKIP (funding={funding_rate:.4f} too high for LONG)")
            return None
        if direction == "SHORT" and funding_rate < -0.002:
            logger.debug(f"  {pair}: SKIP (funding={funding_rate:.4f} too low for SHORT)")
            return None

        # ── Step 10: Confluence Score Calculation ─────────────────
        confluence = self._calc_confluence(
            score_1h=score_1h,
            score_4h=score_4h,
            score_15m=score_15m,
            direction=direction,
            pattern=pattern,
            volume_confirms=volume_confirms,
            regime=regime,
            fg_value=fg_value,
            rsi_val=rsi_val,
            sl_method=sl_method,
        )

        if confluence < self.min_confluence:
            logger.debug(f"  {pair}: LOW CONFLUENCE ({confluence:.0f} < {self.min_confluence})")
            return None

        # ── Step 11: AI Final Confirmation (optional, async) ──────
        ai_approved = await self._ai_confirm(pair, direction, price, sl_price, ta_1h, ta_4h)
        if not ai_approved:
            logger.info(f"  {pair}: AI rejected setup")
            return None

        # ── Step 12: Build setup ──────────────────────────────────
        # Smart TPs: TP1 at 1:1.5 R:R, TP2 at 1:2.5, TP3 at 1:4
        sl_dist = abs(price - sl_price)
        if direction == "LONG":
            tp1 = round(price + sl_dist * 1.5, 6)
            tp2 = round(price + sl_dist * 2.5, 6)
            tp3 = round(price + sl_dist * 4.0, 6)
        else:
            tp1 = round(price - sl_dist * 1.5, 6)
            tp2 = round(price - sl_dist * 2.5, 6)
            tp3 = round(price - sl_dist * 4.0, 6)

        return {
            "pair": pair,
            "side": direction,
            "entry": price,
            "stop_loss": sl_price,
            "sl_dist_pct": round(sl_dist_pct, 3),
            "sl_method": sl_method,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "confluence_score": round(confluence, 1),
            "pattern": pattern.get("pattern", "N/A"),
            "pattern_strength": pattern.get("strength", 0),
            "regime": regime,
            "rsi_1h": round(rsi_val, 1),
            "score_1h": score_1h,
            "score_4h": score_4h,
            "funding_rate": round(funding_rate, 5),
            "volume_ratio": round(vol_ratio, 2),
            "atr_val": round(atr_val, 6),
            "source": "AUTONOMOUS",
            "generated_at": datetime.now().isoformat(),
        }

    def _calc_confluence(
        self, score_1h: float, score_4h: float, score_15m: float,
        direction: str, pattern: Dict, volume_confirms: bool,
        regime: str, fg_value: int, rsi_val: float, sl_method: str
    ) -> float:
        """
        Calculate confluence score 0-100.
        Each factor contributes to a final score.
        Require ≥72 to trade (high bar for high win rate).
        """
        score = 0.0

        # 1. Higher TF scores (most weight — 40 pts max)
        #    Weight 1h × 0.5 + 4h × 0.5 → then scale to 40
        avg_score = (score_1h * 0.5 + score_4h * 0.5)
        if direction == "LONG":
            tf_contrib = (avg_score - 50) / 50 * 40  # 0-40
        else:
            tf_contrib = (50 - avg_score) / 50 * 40
        score += max(0, tf_contrib)

        # 2. 15m entry alignment bonus (10 pts)
        if direction == "LONG" and score_15m >= 60:
            score += 10
        elif direction == "SHORT" and score_15m <= 40:
            score += 10
        elif 45 <= score_15m <= 55:
            score += 3  # Neutral 15m — small bonus (not opposing)

        # 3. Entry pattern (15 pts max)
        if pattern.get("found"):
            strength = pattern.get("strength", 0)
            score += min(15, strength * 0.18)

        # 4. Volume confirmation (8 pts)
        if volume_confirms:
            score += 8
        else:
            score -= 3  # Weak volume = slight penalty

        # 5. Regime alignment (10 pts)
        if (regime == "TRENDING_UP" and direction == "LONG") or \
           (regime == "TRENDING_DOWN" and direction == "SHORT"):
            score += 10
        elif regime == "RANGING":
            score -= 10  # Penalize heavily — ranging = high SL rate

        # 6. Fear & Greed alignment (10 pts max)
        # Extreme fear = strong SHORT signal (panic selling → downtrend)
        # Extreme greed = strong LONG signal (FOMO rally → uptrend)
        if direction == "SHORT" and fg_value <= 15:
            score += 10  # Extreme fear → SHORT is contrarian best play
        elif direction == "LONG" and fg_value >= 88:
            score += 10  # Extreme greed → LONG momentum confirmed
        elif direction == "SHORT" and fg_value < 40:
            score += 7   # Bearish market → SHORT has tailwind
        elif direction == "LONG" and fg_value > 60:
            score += 7   # Bullish market → LONG has tailwind
        elif direction == "LONG" and fg_value <= 25:
            score -= 3   # Mildly risky LONG in fear zone
        elif direction == "SHORT" and fg_value >= 75:
            score -= 3   # Mildly risky SHORT in greed zone

        # 7. RSI sweet spot (10 pts)
        #    LONG: RSI 35-60 = acceptable range (not overbought, has momentum)
        #    SHORT: RSI 40-70 = acceptable range (not oversold, has distribution)
        if direction == "LONG":
            if 38 <= rsi_val <= 58:
                score += 10
            elif 30 <= rsi_val <= 68:
                score += 5
        else:
            if 42 <= rsi_val <= 68:
                score += 10
            elif 30 <= rsi_val <= 75:
                score += 5

        # 8. Smart SL method bonus (5 pts)
        if sl_method == "structure_low" and direction == "LONG":
            score += 5  # SL at key support = more precise
        elif sl_method == "structure_high" and direction == "SHORT":
            score += 5

        return min(100, max(0, score))

    async def _ai_confirm(self, pair: str, side: str, price: float,
                          sl: float, ta_1h: Dict, ta_4h: Dict) -> bool:
        """
        Quick AI gate: ask Groq if setup looks valid.
        Returns True (approve) or False (reject).
        Fast — single call with strict JSON response.
        """
        if not self.groq_client:
            return True  # No AI = pass through (TA already filtered)

        try:
            prompt = f"""You are a conservative crypto futures trader. Review this autonomous setup.

Pair: {pair}
Direction: {side}
Price: ${price:,.4f}
Stop Loss: ${sl:,.4f} ({abs(price-sl)/price*100:.2f}% away)

1h TA Score: {ta_1h.get('score', 50):.0f}/100
1h RSI: {ta_1h.get('rsi', 50):.1f}
1h MACD: {ta_1h.get('macd_cross', 'NEUTRAL')}
1h EMA Cross: {ta_1h.get('ema_cross', 'NEUTRAL')}
4h TA Score: {ta_4h.get('score', 50):.0f}/100
4h RSI: {ta_4h.get('rsi', 50):.1f}
4h MACD: {ta_4h.get('macd_cross', 'NEUTRAL')}

Approve or reject? Respond with JSON only:
{{"approved": true/false, "reason": "brief"}}

Reject if indicators conflict or setup is weak."""

            resp = self.groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=100,
                response_format={"type": "json_object"},
            )
            result = json.loads(resp.choices[0].message.content)
            approved = bool(result.get("approved", False))
            reason = result.get("reason", "")
            logger.info(f"  AI {'✅ APPROVED' if approved else '❌ REJECTED'}: {reason}")
            return approved

        except Exception as e:
            logger.error(f"  AI confirm error: {e}")
            return True  # Fail-open: proceed if AI unavailable

    async def _execute_autonomous_trade(self, setup: Dict) -> bool:
        """Execute an autonomous trade via the shared DB."""
        pair = setup["pair"]
        side = setup["side"]
        price = setup["entry"]
        sl = setup["stop_loss"]
        sl_dist_pct = setup["sl_dist_pct"]

        # Pairs in AUTONOMOUS_PAIRS already have verified candle data from _analyze_pair.
        # No need for a static whitelist check here.

        # Final position size (conservative for autonomous: 1% risk per trade)
        balance = self.db.balance
        risk_pct = float(os.getenv("AUTONOMOUS_RISK_PCT", "0.015"))  # 1.5% risk per auto trade
        risk_amount = balance * risk_pct

        # Leverage: cap at 10x for autonomous (more conservative than signal trading)
        max_auto_leverage = int(os.getenv("AUTONOMOUS_MAX_LEVERAGE", "10"))
        leverage = min(max_auto_leverage, max(2, int(15 / max(sl_dist_pct, 0.5))))

        position_value = risk_amount / (sl_dist_pct / 100)
        max_position = balance * leverage
        position_value = min(position_value, max_position)
        margin = position_value / leverage
        margin = min(margin, balance * 0.25)  # Never more than 25% of balance per trade
        position_value = margin * leverage
        quantity = position_value / price

        if margin < 1 or margin > balance:
            logger.info(f"  AUTO SKIP: margin=${margin:.2f} invalid (balance=${balance:.2f})")
            return False

        trade = {
            "symbol": pair,
            "side": side,
            "action": side,
            "entry_price": price,
            "quantity": round(quantity, 6),
            "leverage": leverage,
            "margin": round(margin, 2),
            "position_value": round(position_value, 2),
            "stop_loss": sl,
            "tp1": setup["tp1"],
            "tp2": setup["tp2"],
            "tp3": setup["tp3"],
            "sl_pct": sl_dist_pct,
            "confidence": setup["confluence_score"] / 100,
            "reasoning": (
                f"AUTO | confluence={setup['confluence_score']:.0f} | "
                f"pattern={setup.get('pattern', 'N/A')} | "
                f"regime={setup.get('regime', '?')} | "
                f"sl_method={setup.get('sl_method', '?')}"
            ),
            "model": "AUTONOMOUS_ENGINE",
            "ta_score": setup["score_1h"],
        }

        result = self.db.open_trade(trade)
        trade_id = result.get("id") if isinstance(result, dict) else result

        if trade_id:
            logger.info(
                f"  🤖 AUTO TRADE #{trade_id}: {side} {pair} @ ${price:,.4f} | "
                f"{leverage}x | margin=${margin:.2f} | SL=${sl:,.6f} ({sl_dist_pct:.2f}%) | "
                f"confluence={setup['confluence_score']:.0f}"
            )
            self.tg_send(
                f"🤖 <b>AUTO TRADE OPENED</b>\n"
                f"{side} {pair} @ ${price:,.4f}\n"
                f"Leverage: {leverage}x | Margin: ${margin:.2f}\n"
                f"SL: ${sl:,.4f} ({sl_dist_pct:.2f}%) [{setup.get('sl_method', '?')}]\n"
                f"TP1: ${setup['tp1']:,.4f} | TP2: ${setup['tp2']:,.4f}\n"
                f"Confluence: {setup['confluence_score']:.0f}/100\n"
                f"Pattern: {setup.get('pattern', 'N/A')} | Regime: {setup.get('regime', '?')}\n"
                f"Source: Autonomous Engine"
            )
            return True

        return False

    def get_status(self) -> Dict:
        return {
            "scans": self.scan_count,
            "setups_found": self.setups_found,
            "auto_trades": self.auto_trades,
            "pairs_monitored": len(AUTONOMOUS_PAIRS),
            "min_confluence": self.min_confluence,
        }
