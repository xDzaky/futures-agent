"""
Technical Analysis — Indicator Engine
=======================================
Computes TA indicators using pure pandas (no pandas-ta):
- RSI, MACD, Bollinger Bands, EMA, ATR
- Volume analysis, momentum
- Multi-timeframe scoring
- Signal generation (LONG/SHORT/SKIP)
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, Optional

logger = logging.getLogger("technical")


# ─── Pure Pandas Indicator Functions ───────────────────

def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26,
         signal: int = 9) -> pd.DataFrame:
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return pd.DataFrame({
        "macd": macd_line,
        "histogram": histogram,
        "signal": signal_line,
    })


def bollinger_bands(series: pd.Series, length: int = 20,
                    std: float = 2.0) -> pd.DataFrame:
    mid = series.rolling(length).mean()
    rolling_std = series.rolling(length).std()
    upper = mid + std * rolling_std
    lower = mid - std * rolling_std
    return pd.DataFrame({"upper": upper, "mid": mid, "lower": lower})


def atr(high: pd.Series, low: pd.Series, close: pd.Series,
        length: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1/length, min_periods=length, adjust=False).mean()


def stoch_rsi(series: pd.Series, length: int = 14,
              k_period: int = 3) -> pd.Series:
    rsi_vals = rsi(series, length)
    min_rsi = rsi_vals.rolling(length).min()
    max_rsi = rsi_vals.rolling(length).max()
    denom = max_rsi - min_rsi
    stoch = ((rsi_vals - min_rsi) / denom.replace(0, np.nan)) * 100
    return stoch.rolling(k_period).mean()


class TechnicalAnalyzer:
    """Technical analysis indicator computation and signal scoring."""

    def analyze(self, df: pd.DataFrame, timeframe: str = "5m") -> Dict:
        """
        Run full technical analysis on a candle DataFrame.
        Returns indicator values + directional signal.
        """
        if df is None or df.empty or len(df) < 30:
            return {"signal": "SKIP", "score": 0, "reason": "Insufficient data"}

        indicators = {}

        # ─── Trend Indicators ──────────────

        # EMA Cross (9/21)
        df = df.copy()
        df["ema_9"] = ema(df["close"], 9)
        df["ema_21"] = ema(df["close"], 21)
        df["ema_50"] = ema(df["close"], 50)

        ema_9 = df["ema_9"].iloc[-1]
        ema_21 = df["ema_21"].iloc[-1]
        ema_50 = df["ema_50"].iloc[-1] if not pd.isna(df["ema_50"].iloc[-1]) else ema_21
        price = df["close"].iloc[-1]

        indicators["ema_cross"] = "BULLISH" if ema_9 > ema_21 else "BEARISH"
        indicators["price_vs_ema50"] = "ABOVE" if price > ema_50 else "BELOW"

        # ─── Momentum Indicators ───────────

        # RSI
        rsi_series = rsi(df["close"], 14)
        rsi_val = rsi_series.iloc[-1] if rsi_series is not None and not rsi_series.empty else 50
        if pd.isna(rsi_val):
            rsi_val = 50
        indicators["rsi"] = round(float(rsi_val), 2)
        if rsi_val > 70:
            indicators["rsi_signal"] = "OVERBOUGHT"
        elif rsi_val < 30:
            indicators["rsi_signal"] = "OVERSOLD"
        else:
            indicators["rsi_signal"] = "NEUTRAL"

        # MACD
        macd_df = macd(df["close"], 12, 26, 9)
        if macd_df is not None and not macd_df.empty:
            macd_line = macd_df["macd"].iloc[-1]
            signal_line = macd_df["signal"].iloc[-1]
            macd_hist = macd_df["histogram"].iloc[-1]
            indicators["macd_line"] = round(float(macd_line), 4)
            indicators["macd_signal"] = round(float(signal_line), 4)
            indicators["macd_histogram"] = round(float(macd_hist), 4)
            indicators["macd_cross"] = "BULLISH" if macd_line > signal_line else "BEARISH"
        else:
            indicators["macd_cross"] = "NEUTRAL"
            indicators["macd_histogram"] = 0

        # Stochastic RSI
        stoch_series = stoch_rsi(df["close"], 14)
        if stoch_series is not None and not stoch_series.empty:
            stoch_k = stoch_series.iloc[-1]
            indicators["stoch_rsi"] = round(float(stoch_k), 2) if not pd.isna(stoch_k) else 50
        else:
            indicators["stoch_rsi"] = 50

        # ─── Volatility Indicators ─────────

        # Bollinger Bands
        bb = bollinger_bands(df["close"], 20, 2)
        if bb is not None and not bb.empty:
            bb_upper = bb["upper"].iloc[-1]
            bb_mid = bb["mid"].iloc[-1]
            bb_lower = bb["lower"].iloc[-1]
            if not pd.isna(bb_upper) and not pd.isna(bb_lower) and bb_mid > 0:
                bb_width = (bb_upper - bb_lower) / bb_mid
                indicators["bb_upper"] = round(float(bb_upper), 4)
                indicators["bb_lower"] = round(float(bb_lower), 4)
                indicators["bb_width"] = round(float(bb_width), 4)

                if price > bb_upper:
                    indicators["bb_signal"] = "OVERBOUGHT"
                elif price < bb_lower:
                    indicators["bb_signal"] = "OVERSOLD"
                else:
                    indicators["bb_signal"] = "NEUTRAL"
            else:
                indicators["bb_signal"] = "NEUTRAL"
                indicators["bb_width"] = 0
        else:
            indicators["bb_signal"] = "NEUTRAL"
            indicators["bb_width"] = 0

        # ATR (Average True Range)
        atr_series = atr(df["high"], df["low"], df["close"], 14)
        if atr_series is not None and not atr_series.empty:
            atr_val = atr_series.iloc[-1]
            if not pd.isna(atr_val):
                atr_pct = (atr_val / price * 100) if price > 0 else 0
                indicators["atr"] = round(float(atr_val), 4)
                indicators["atr_pct"] = round(float(atr_pct), 2)
                indicators["volatility"] = (
                    "HIGH" if atr_pct > 2 else
                    "MEDIUM" if atr_pct > 1 else "LOW"
                )
            else:
                indicators["atr_pct"] = 0
                indicators["volatility"] = "UNKNOWN"
        else:
            indicators["atr_pct"] = 0
            indicators["volatility"] = "UNKNOWN"

        # ─── Volume Analysis ──────────────

        avg_vol = df["volume"].rolling(20).mean().iloc[-1]
        curr_vol = df["volume"].iloc[-1]
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1
        indicators["volume_ratio"] = round(float(vol_ratio), 2)
        indicators["volume_signal"] = (
            "HIGH" if vol_ratio > 1.5 else
            "LOW" if vol_ratio < 0.5 else "NORMAL"
        )

        # ─── Price Action ─────────────────

        # Recent candle patterns
        last_3 = df.tail(3)
        bullish_candles = sum(1 for _, c in last_3.iterrows() if c["close"] > c["open"])
        indicators["recent_bias"] = "BULLISH" if bullish_candles >= 2 else (
            "BEARISH" if bullish_candles <= 1 else "MIXED"
        )

        # Price change
        change_5 = (price - df["close"].iloc[-6]) / df["close"].iloc[-6] * 100
        change_20 = (price - df["close"].iloc[-21]) / df["close"].iloc[-21] * 100 if len(df) > 21 else 0
        indicators["change_5_bars"] = round(float(change_5), 2)
        indicators["change_20_bars"] = round(float(change_20), 2)

        # ─── Composite Score ──────────────

        score = self._compute_score(indicators)
        indicators["score"] = score

        if score >= 65:
            indicators["signal"] = "LONG"
        elif score <= 35:
            indicators["signal"] = "SHORT"
        else:
            indicators["signal"] = "SKIP"

        indicators["timeframe"] = timeframe
        indicators["price"] = round(float(price), 4)

        return indicators

    def _compute_score(self, ind: Dict) -> int:
        """
        Compute directional score 0-100.
        >65 = LONG signal, <35 = SHORT signal, 35-65 = SKIP.
        """
        score = 50  # Start neutral

        # EMA trend (+/- 10)
        if ind.get("ema_cross") == "BULLISH":
            score += 10
        elif ind.get("ema_cross") == "BEARISH":
            score -= 10

        # Price vs EMA50 (+/- 5)
        if ind.get("price_vs_ema50") == "ABOVE":
            score += 5
        else:
            score -= 5

        # RSI (+/- 10)
        rsi_val = ind.get("rsi", 50)
        if rsi_val < 30:
            score += 10  # Oversold = bullish reversal
        elif rsi_val > 70:
            score -= 10  # Overbought = bearish reversal
        elif rsi_val < 45:
            score += 3
        elif rsi_val > 55:
            score -= 3

        # MACD (+/- 8)
        if ind.get("macd_cross") == "BULLISH":
            score += 8
        elif ind.get("macd_cross") == "BEARISH":
            score -= 8

        # MACD histogram momentum (+/- 5)
        hist = ind.get("macd_histogram", 0)
        if hist > 0:
            score += 5
        elif hist < 0:
            score -= 5

        # Bollinger Bands (+/- 7)
        if ind.get("bb_signal") == "OVERSOLD":
            score += 7
        elif ind.get("bb_signal") == "OVERBOUGHT":
            score -= 7

        # Volume confirmation (+/- 5)
        if ind.get("volume_signal") == "HIGH":
            if ind.get("ema_cross") == "BULLISH":
                score += 5
            elif ind.get("ema_cross") == "BEARISH":
                score -= 5

        # Recent price action (+/- 5)
        if ind.get("recent_bias") == "BULLISH":
            score += 5
        elif ind.get("recent_bias") == "BEARISH":
            score -= 5

        return max(0, min(100, score))

    def multi_timeframe_analysis(self, candles_by_tf: Dict[str, pd.DataFrame]) -> Dict:
        """
        Analyze multiple timeframes and produce consensus signal.
        Higher timeframes get more weight.
        """
        weights = {"1m": 0.05, "5m": 0.15, "15m": 0.25, "1h": 0.30, "4h": 0.25}
        total_score = 0
        total_weight = 0
        tf_results = {}

        for tf, df in candles_by_tf.items():
            result = self.analyze(df, tf)
            tf_results[tf] = result
            weight = weights.get(tf, 0.1)
            total_score += result.get("score", 50) * weight
            total_weight += weight

        if total_weight > 0:
            consensus_score = total_score / total_weight
        else:
            consensus_score = 50

        if consensus_score >= 60:
            consensus = "LONG"
        elif consensus_score <= 40:
            consensus = "SHORT"
        else:
            consensus = "SKIP"

        # Agreement filter: count how many TFs agree on direction
        long_count = sum(1 for r in tf_results.values() if r.get("signal") == "LONG")
        short_count = sum(1 for r in tf_results.values() if r.get("signal") == "SHORT")
        total_tf = len(tf_results)

        # Require at least 40% of timeframes to agree
        if consensus == "LONG" and long_count < total_tf * 0.4:
            consensus = "SKIP"
        elif consensus == "SHORT" and short_count < total_tf * 0.4:
            consensus = "SKIP"

        return {
            "consensus": consensus,
            "consensus_score": round(consensus_score, 1),
            "timeframes": tf_results,
            "tf_agreement": max(long_count, short_count) / max(1, total_tf),
        }

    def calculate_sl_tp(self, price: float, side: str,
                        atr_val: float, risk_reward: float = 2.0) -> Dict:
        """
        Calculate SL and TP levels based on ATR.
        - SL: 2.0x ATR from entry (wider = fewer false stops)
        - TP1: 1.2x SL distance (hit more often)
        - TP2: 2.0x SL distance
        - TP3: 3.5x SL distance
        """
        sl_distance = atr_val * 2.0

        if side == "LONG":
            sl = price - sl_distance
            tp1 = price + sl_distance * 1.2
            tp2 = price + sl_distance * 2.0
            tp3 = price + sl_distance * 3.5
        else:  # SHORT
            sl = price + sl_distance
            tp1 = price - sl_distance * 1.2
            tp2 = price - sl_distance * 2.0
            tp3 = price - sl_distance * 3.5

        return {
            "entry": round(price, 4),
            "stop_loss": round(sl, 4),
            "tp1": round(tp1, 4),
            "tp2": round(tp2, 4),
            "tp3": round(tp3, 4),
            "sl_distance_pct": round(sl_distance / price * 100, 2),
            "risk_reward": risk_reward,
        }
