"""
Backtester — Historical Strategy Testing
===========================================
Replays historical candle data bar-by-bar through the same
TA pipeline used by the live agent. Simulates SL/TP hits on
every bar to produce realistic backtest results.

Two modes:
  1. TA-only  (fast, ~1000 bars/sec, no API calls)
  2. TA + AI  (slower, sends high-score signals to Groq for confirmation)

Usage:
  python backtester.py                        # 7-day BTC, TA-only
  python backtester.py --days 30              # 30-day backtest
  python backtester.py --pair ETH/USDT        # different pair
  python backtester.py --pairs BTC/USDT,ETH/USDT,SOL/USDT  # multi-pair
  python backtester.py --ai                   # enable AI confirmation
  python backtester.py --timeframe 15m        # change signal timeframe
"""

import os
import sys
import time
import argparse
import logging
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

from technical import TechnicalAnalyzer
from risk_manager import RiskManager

load_dotenv()
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("backtester")


# ─── Colors ────────────────────────────────────────────
class C:
    G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; CY = "\033[96m"
    M = "\033[95m"; W = "\033[97m"; D = "\033[2m"; B = "\033[1m"
    RST = "\033[0m"


# ─── Data Downloader ───────────────────────────────────

def download_candles(symbol: str, timeframe: str, days: int) -> pd.DataFrame:
    """
    Download historical candles. Tries multiple sources:
    1. Binance Futures (fastest, highest resolution)
    2. CryptoCompare (free, no geo-blocks, reliable fallback)
    """
    # Try Binance first
    df = _download_binance(symbol, timeframe, days)
    if not df.empty:
        return df

    # Fallback to CryptoCompare
    print(f"  Binance unavailable, falling back to CryptoCompare...")
    df = _download_cryptocompare(symbol, timeframe, days)
    return df


def _download_binance(symbol: str, timeframe: str, days: int) -> pd.DataFrame:
    """Try Binance Futures API."""
    pair = symbol.replace("/", "").replace(":USDT", "")
    url = "https://fapi.binance.com/fapi/v1/klines"
    tf_minutes = _tf_to_minutes(timeframe)
    total_bars = int(days * 24 * 60 / tf_minutes)
    all_candles = []
    end_time = int(time.time() * 1000)

    print(f"  Trying Binance: {symbol} {timeframe} — {days} days ({total_bars} bars)...")

    while len(all_candles) < total_bars:
        limit = min(1500, total_bars - len(all_candles))
        params = {"symbol": pair, "interval": timeframe, "limit": limit, "endTime": end_time}
        try:
            resp = requests.get(url, params=params, timeout=8)
            if resp.status_code != 200:
                break
            data = resp.json()
            if not data:
                break
            all_candles = data + all_candles
            end_time = data[0][0] - 1
            time.sleep(0.2)
        except Exception:
            break

    if not all_candles:
        return pd.DataFrame()

    df = pd.DataFrame(all_candles, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore",
    ])
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    print(f"  Got {len(df)} candles from Binance")
    return df


def _download_cryptocompare(symbol: str, timeframe: str, days: int) -> pd.DataFrame:
    """
    Download from CryptoCompare (free, no geo-blocks).
    Supports: histominute (1m,5m,15m), histohour (1h,4h), histoday.
    CryptoCompare max 2000 per request. For minute data we aggregate.
    """
    coin = symbol.split("/")[0]
    quote = symbol.split("/")[1] if "/" in symbol else "USDT"
    tf_minutes = _tf_to_minutes(timeframe)

    # CryptoCompare endpoints
    if tf_minutes < 60:
        # Minute-level data: use histominute, then resample
        endpoint = "histominute"
        raw_bars = days * 24 * 60  # total 1m bars
        aggregate = tf_minutes  # resample factor
    elif tf_minutes < 1440:
        endpoint = "histohour"
        raw_bars = days * 24
        aggregate = tf_minutes // 60
    else:
        endpoint = "histoday"
        raw_bars = days
        aggregate = 1

    # For minute data, CryptoCompare free tier limits to 7 days
    # We paginate with toTs parameter
    url = f"https://min-api.cryptocompare.com/data/v2/{endpoint}"
    all_data = []
    to_ts = int(time.time())

    # Limit: 2000 per request
    per_request = 2000
    remaining = raw_bars

    print(f"  Downloading {symbol} via CryptoCompare ({endpoint}, {days} days)...")

    while remaining > 0:
        limit = min(per_request, remaining)
        params = {"fsym": coin, "tsym": quote, "limit": limit, "toTs": to_ts}
        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                print(f"  CryptoCompare error: {resp.status_code}")
                break
            result = resp.json()
            data = result.get("Data", {}).get("Data", [])
            if not data:
                break
            all_data = data + all_data
            to_ts = data[0]["time"] - 1
            remaining -= len(data)
            time.sleep(0.3)
        except Exception as e:
            print(f"  CryptoCompare error: {e}")
            break

    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df["timestamp"] = pd.to_datetime(df["time"], unit="s")
    df = df.rename(columns={"volumefrom": "volume"})
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    # Remove zero-price rows
    df = df[df["close"] > 0].copy()

    # Resample if needed (e.g., 1m → 5m)
    if aggregate > 1 and endpoint == "histominute":
        df = df.set_index("timestamp")
        df = df.resample(f"{tf_minutes}min").agg({
            "open": "first", "high": "max", "low": "min",
            "close": "last", "volume": "sum",
        }).dropna().reset_index()
    elif aggregate > 1 and endpoint == "histohour":
        df = df.set_index("timestamp")
        df = df.resample(f"{tf_minutes // 60}h").agg({
            "open": "first", "high": "max", "low": "min",
            "close": "last", "volume": "sum",
        }).dropna().reset_index()

    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    print(f"  Got {len(df)} candles from CryptoCompare: {df['timestamp'].iloc[0]} → {df['timestamp'].iloc[-1]}")
    return df


def _tf_to_minutes(tf: str) -> int:
    multipliers = {"m": 1, "h": 60, "d": 1440, "w": 10080}
    unit = tf[-1]
    val = int(tf[:-1])
    return val * multipliers.get(unit, 1)


# ─── Simulated Trade ──────────────────────────────────

class BacktestTrade:
    __slots__ = [
        "id", "symbol", "side", "entry_price", "entry_time",
        "quantity", "margin", "leverage", "position_value",
        "stop_loss", "tp1", "tp2", "tp3",
        "sl_pct", "confidence", "ta_score",
        "exit_price", "exit_time", "profit", "profit_pct",
        "fee", "reason", "status", "max_favorable", "max_adverse",
    ]

    def __init__(self, **kwargs):
        for k in self.__slots__:
            setattr(self, k, kwargs.get(k, 0))
        self.status = "OPEN"
        self.max_favorable = 0.0
        self.max_adverse = 0.0


# ─── Backtester Engine ─────────────────────────────────

class Backtester:
    """Event-driven backtester that replays candles through the TA engine."""

    def __init__(self, starting_balance: float = 1000.0,
                 max_risk: float = 0.02, max_leverage: int = 10,
                 max_positions: int = 3, use_ai: bool = False,
                 signal_timeframe: str = "5m"):

        self.starting_balance = starting_balance
        self.balance = starting_balance
        self.max_risk = max_risk
        self.max_leverage = max_leverage
        self.max_positions = max_positions
        self.use_ai = use_ai
        self.signal_tf = signal_timeframe

        # Modules
        self.ta = TechnicalAnalyzer()
        self.risk = RiskManager()

        # AI (optional)
        self.ai = None
        if self.use_ai:
            try:
                from ai_analyzer import AIAnalyzer
                self.ai = AIAnalyzer()
                print(f"  {C.CY}AI mode enabled (Groq){C.RST}")
            except Exception as e:
                print(f"  AI init failed: {e}, using TA-only")

        # State
        self.trades: List[BacktestTrade] = []
        self.open_trades: List[BacktestTrade] = []
        self.equity_curve: List[Dict] = []
        self.trade_counter = 0
        self.total_fees = 0.0
        self.peak_balance = starting_balance
        self.max_drawdown = 0.0
        self.daily_pnl: Dict[str, float] = {}
        self.consecutive_losses = 0  # Track consecutive losses for cooldown

    def run(self, candles: pd.DataFrame, symbol: str):
        """Run backtest on a single pair."""
        if candles.empty or len(candles) < 60:
            print(f"  Not enough data for {symbol}")
            return

        lookback = 55  # Minimum bars needed for TA (EMA50 + buffer)
        total = len(candles)
        last_signal_bar = -10  # Prevent rapid-fire signals

        print(f"\n  {C.B}Running backtest: {symbol}{C.RST}")
        print(f"  Bars: {total} | Lookback: {lookback} | Balance: ${self.balance:.2f}")
        print(f"  {'─'*55}")

        for i in range(lookback, total):
            bar = candles.iloc[i]
            bar_time = bar["timestamp"]
            price = bar["close"]
            high = bar["high"]
            low = bar["low"]

            # ── Monitor open positions (check SL/TP on this bar) ──
            self._check_exits(high, low, price, bar_time, i)

            # ── Record equity ──
            unrealized = self._calc_unrealized(price)
            equity = self.balance + unrealized
            self.equity_curve.append({
                "bar": i,
                "timestamp": bar_time,
                "balance": self.balance,
                "equity": equity,
                "open_positions": len(self.open_trades),
            })

            # Track drawdown
            if equity > self.peak_balance:
                self.peak_balance = equity
            dd = (self.peak_balance - equity) / self.peak_balance * 100
            if dd > self.max_drawdown:
                self.max_drawdown = dd

            # ── Skip if too many positions or too close to last signal ──
            if len(self.open_trades) >= self.max_positions:
                continue
            if i - last_signal_bar < 12:  # Min 12 bars (1 hour on 5m) between signals
                continue

            # ── Consecutive loss cooldown ──
            if self.consecutive_losses >= 3 and i - last_signal_bar < 30:
                continue  # Wait longer after 3 consecutive losses

            # ── Check for symbol already open ──
            if any(t.symbol == symbol for t in self.open_trades):
                continue

            # ── TA Analysis ──
            window = candles.iloc[max(0, i - lookback):i + 1].copy()
            ta_result = self.ta.analyze(window, self.signal_tf)
            signal = ta_result.get("signal", "SKIP")
            score = ta_result.get("score", 50)

            if signal == "SKIP":
                continue

            # Set confidence from TA score
            confidence = min(0.95, score / 100) if signal == "LONG" else min(0.95, (100 - score) / 100)

            # ── Require minimum confidence ──
            if confidence < 0.68:
                continue

            # ── Volume filter: skip if volume is too low ──
            vol_signal = ta_result.get("volume_signal", "NORMAL")
            if vol_signal == "LOW":
                continue

            # ── AI Confirmation (optional) ──
            if self.use_ai and self.ai:
                ai_decision = self._ai_confirm(symbol, ta_result, price)
                if ai_decision == "SKIP":
                    continue
                if ai_decision != signal:
                    continue  # AI disagrees with TA

            # ── Position Sizing ──
            side = signal
            atr_val = ta_result.get("atr", price * 0.01)
            levels = self.ta.calculate_sl_tp(price, side, atr_val)

            sl_dist_pct = levels["sl_distance_pct"]
            leverage = self._calc_leverage(confidence, sl_dist_pct)

            pos = self.risk.calculate_position(
                self.balance, price, sl_dist_pct, leverage, confidence
            )

            margin = pos["margin_required"]
            if margin > self.balance * 0.5 or margin < 1:
                continue

            # ── Open Trade ──
            self.trade_counter += 1
            fee = pos["position_value"] * 0.0004  # 0.04% taker

            trade = BacktestTrade(
                id=self.trade_counter,
                symbol=symbol,
                side=side,
                entry_price=price,
                entry_time=bar_time,
                quantity=pos["quantity"],
                margin=margin,
                leverage=leverage,
                position_value=pos["position_value"],
                stop_loss=levels["stop_loss"],
                tp1=levels["tp1"],
                tp2=levels["tp2"],
                tp3=levels["tp3"],
                sl_pct=sl_dist_pct,
                confidence=confidence,
                ta_score=score,
                fee=fee,
            )

            self.balance -= (margin + fee)
            self.total_fees += fee
            self.open_trades.append(trade)
            last_signal_bar = i

        # ── Close remaining open trades at last price ──
        last_price = candles["close"].iloc[-1]
        last_time = candles["timestamp"].iloc[-1]
        for t in list(self.open_trades):
            self._close_trade(t, last_price, last_time, "END_OF_DATA")

    def run_multi(self, pairs_data: Dict[str, pd.DataFrame]):
        """Run backtest across multiple pairs using merged timeline."""
        # Collect all unique timestamps
        all_times = set()
        for df in pairs_data.values():
            all_times.update(df["timestamp"].tolist())
        all_times = sorted(all_times)

        if not all_times:
            print("No data to backtest")
            return

        # Build indexed lookups
        indexed = {}
        for symbol, df in pairs_data.items():
            indexed[symbol] = df.set_index("timestamp")

        lookback = 55
        last_signal_bar = {}
        bar_count = 0

        print(f"\n  {C.B}Multi-pair backtest: {', '.join(pairs_data.keys())}{C.RST}")
        print(f"  Timeline: {len(all_times)} bars | Balance: ${self.balance:.2f}")
        print(f"  {'─'*55}")

        for t_idx, ts in enumerate(all_times):
            bar_count += 1

            # ── Check exits for all open positions ──
            for t in list(self.open_trades):
                sym_df = indexed.get(t.symbol)
                if sym_df is None or ts not in sym_df.index:
                    continue
                bar = sym_df.loc[ts]
                if isinstance(bar, pd.DataFrame):
                    bar = bar.iloc[0]
                self._check_single_exit(t, bar["high"], bar["low"], bar["close"], ts, t_idx)

            # ── Equity tracking ──
            unrealized = 0
            for t in self.open_trades:
                sym_df = indexed.get(t.symbol)
                if sym_df is not None and ts in sym_df.index:
                    row = sym_df.loc[ts]
                    cp = row["close"] if not isinstance(row, pd.DataFrame) else row.iloc[0]["close"]
                    if t.side == "LONG":
                        unrealized += t.margin * ((cp - t.entry_price) / t.entry_price) * t.leverage
                    else:
                        unrealized += t.margin * ((t.entry_price - cp) / t.entry_price) * t.leverage

            equity = self.balance + unrealized
            self.equity_curve.append({"bar": bar_count, "timestamp": ts, "balance": self.balance, "equity": equity, "open_positions": len(self.open_trades)})
            if equity > self.peak_balance:
                self.peak_balance = equity
            dd = (self.peak_balance - equity) / self.peak_balance * 100
            if dd > self.max_drawdown:
                self.max_drawdown = dd

            # ── Scan pairs for signals ──
            if len(self.open_trades) >= self.max_positions:
                continue

            for symbol, sym_df in indexed.items():
                if any(ot.symbol == symbol for ot in self.open_trades):
                    continue
                if symbol in last_signal_bar and t_idx - last_signal_bar[symbol] < 5:
                    continue

                # Need enough history
                mask = sym_df.index <= ts
                available = sym_df[mask]
                if len(available) < lookback:
                    continue

                window = available.iloc[-lookback:].reset_index()
                price = window["close"].iloc[-1]
                ta_result = self.ta.analyze(window, self.signal_tf)
                signal = ta_result.get("signal", "SKIP")
                score = ta_result.get("score", 50)

                if signal == "SKIP":
                    continue

                confidence = min(0.95, score / 100) if signal == "LONG" else min(0.95, (100 - score) / 100)

                if self.use_ai and self.ai:
                    ai_decision = self._ai_confirm(symbol, ta_result, price)
                    if ai_decision == "SKIP" or ai_decision != signal:
                        continue

                side = signal
                atr_val = ta_result.get("atr", price * 0.01)
                levels = self.ta.calculate_sl_tp(price, side, atr_val)
                sl_dist_pct = levels["sl_distance_pct"]
                leverage = self._calc_leverage(confidence, sl_dist_pct)
                pos = self.risk.calculate_position(self.balance, price, sl_dist_pct, leverage, confidence)
                margin = pos["margin_required"]

                if margin > self.balance * 0.5 or margin < 1:
                    continue

                self.trade_counter += 1
                fee = pos["position_value"] * 0.0004

                trade = BacktestTrade(
                    id=self.trade_counter, symbol=symbol, side=side,
                    entry_price=price, entry_time=ts,
                    quantity=pos["quantity"], margin=margin, leverage=leverage,
                    position_value=pos["position_value"],
                    stop_loss=levels["stop_loss"], tp1=levels["tp1"],
                    tp2=levels["tp2"], tp3=levels["tp3"],
                    sl_pct=sl_dist_pct, confidence=confidence,
                    ta_score=score, fee=fee,
                )

                self.balance -= (margin + fee)
                self.total_fees += fee
                self.open_trades.append(trade)
                last_signal_bar[symbol] = t_idx

                if len(self.open_trades) >= self.max_positions:
                    break

        # Close remaining
        for t in list(self.open_trades):
            sym_df = indexed.get(t.symbol)
            if sym_df is not None and len(sym_df) > 0:
                last = sym_df.iloc[-1]
                self._close_trade(t, last["close"], sym_df.index[-1], "END_OF_DATA")

    def _check_exits(self, high: float, low: float, close: float,
                     bar_time, bar_idx: int):
        """Check SL/TP for all open trades on current bar."""
        for t in list(self.open_trades):
            self._check_single_exit(t, high, low, close, bar_time, bar_idx)

    def _check_single_exit(self, t: BacktestTrade, high: float, low: float,
                           close: float, bar_time, bar_idx: int):
        """Check SL/TP for a single trade."""
        if t.side == "LONG":
            # Track MFE/MAE
            favorable = (high - t.entry_price) / t.entry_price * 100
            adverse = (t.entry_price - low) / t.entry_price * 100
            t.max_favorable = max(t.max_favorable, favorable)
            t.max_adverse = max(t.max_adverse, adverse)

            # Stop loss
            if low <= t.stop_loss:
                self._close_trade(t, t.stop_loss, bar_time, "STOP_LOSS")
                return
            # TP1
            if high >= t.tp1:
                self._close_trade(t, t.tp1, bar_time, "TP1")
                return

        else:  # SHORT
            favorable = (t.entry_price - low) / t.entry_price * 100
            adverse = (high - t.entry_price) / t.entry_price * 100
            t.max_favorable = max(t.max_favorable, favorable)
            t.max_adverse = max(t.max_adverse, adverse)

            # Stop loss
            if high >= t.stop_loss:
                self._close_trade(t, t.stop_loss, bar_time, "STOP_LOSS")
                return
            # TP1
            if low <= t.tp1:
                self._close_trade(t, t.tp1, bar_time, "TP1")
                return

    def _close_trade(self, t: BacktestTrade, exit_price: float,
                     exit_time, reason: str):
        """Close a trade and update balance."""
        if t.side == "LONG":
            pnl_pct = (exit_price - t.entry_price) / t.entry_price * 100
        else:
            pnl_pct = (t.entry_price - exit_price) / t.entry_price * 100

        profit = t.margin * (pnl_pct / 100) * t.leverage
        exit_fee = t.position_value * 0.0004
        net = profit - exit_fee

        t.exit_price = exit_price
        t.exit_time = exit_time
        t.profit = net
        t.profit_pct = pnl_pct
        t.fee += exit_fee
        t.reason = reason
        t.status = "WIN" if net > 0 else "LOSS"

        self.balance += (t.margin + net)
        self.total_fees += exit_fee

        # Track consecutive losses for cooldown
        if net > 0:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1

        # Daily P&L
        day = str(exit_time)[:10]
        self.daily_pnl[day] = self.daily_pnl.get(day, 0) + net

        if t in self.open_trades:
            self.open_trades.remove(t)
        self.trades.append(t)

    def _calc_unrealized(self, current_price: float) -> float:
        total = 0
        for t in self.open_trades:
            if t.side == "LONG":
                pct = (current_price - t.entry_price) / t.entry_price
            else:
                pct = (t.entry_price - current_price) / t.entry_price
            total += t.margin * pct * t.leverage
        return total

    def _calc_leverage(self, confidence: float, sl_pct: float) -> int:
        if confidence >= 0.90:
            lev = 5
        elif confidence >= 0.80:
            lev = 4
        elif confidence >= 0.70:
            lev = 3
        else:
            lev = 2

        if sl_pct > 3:
            lev = min(lev, 2)
        elif sl_pct > 2:
            lev = min(lev, 3)

        return min(lev, self.max_leverage)

    def _ai_confirm(self, symbol: str, ta_result: dict,
                    price: float) -> str:
        """
        Ask AI to confirm TA signal.
        Uses Multi-AI Consensus (Groq + NVIDIA) if available.
        """
        if not self.ai:
            return ta_result.get("signal", "SKIP")
            
        try:
            # 1. Primary Analysis (Groq)
            market_ctx = {
                "symbol": symbol, 
                "price": price, 
                "orderbook": {"imbalance": 0, "signal": "NEUTRAL"}, # Sim
                "funding": {"rate": 0.0001}
            }
            
            groq_result = self.ai.analyze_trade(symbol, ta_result, market_ctx, "")
            
            if not groq_result or groq_result.get("action") == "SKIP":
                return "SKIP"
                
            groq_action = groq_result.get("action")
            
            # 2. Consensus Validation (NVIDIA DeepSeek)
            # We initialize validator here lazily or check if it exists
            # For backtesting, we'll instantiate it once if needed, or just use it here
            if not hasattr(self, 'validator'):
                try:
                    from consensus_validator import ConsensusValidator
                    self.validator = ConsensusValidator()
                except ImportError:
                    self.validator = None
                    
            if self.validator and self.validator.enable_consensus:
                # Construct signal object for validator
                signal_candidate = {
                    "pair": symbol,
                    "side": groq_action,
                    "entry": price,
                    "stop_loss": price * (0.98 if groq_action == "LONG" else 1.02), # Estimate
                    "targets": [],
                    "leverage": groq_result.get("leverage", 5),
                    "confidence": groq_result.get("confidence", 0.7),
                    "reasoning": groq_result.get("reasoning", "")
                }
                
                # Context strictly for validation
                context = {
                    "technical": ta_result,
                    "market": market_ctx,
                    "news": ""
                }
                
                # Validate
                validated = self.validator.validate_signal(signal_candidate, context)
                if not validated:
                    # Validator rejected it
                    print(f"  {C.R}AI Validator REJECTED {symbol} {groq_action} (Consensus Failed){C.RST}")
                    return "SKIP"
                    
                # Validator approved/improved it
                print(f"  {C.G}AI Validator APPROVED {symbol} {groq_action} (Consensus Reached){C.RST}")
                # If validated["consensus"]["agreed"] is False, it returns None, so we are safe
                
            return groq_action
            
        except Exception as e:
            # logger.error(f"AI confirmation failed: {e}")
            pass
            
        return ta_result.get("signal", "SKIP")

    # ─── Report ────────────────────────────────────────

    def report(self):
        """Generate comprehensive backtest report."""
        closed = [t for t in self.trades if t.status in ("WIN", "LOSS")]
        wins = [t for t in closed if t.status == "WIN"]
        losses = [t for t in closed if t.status == "LOSS"]

        total_closed = len(closed)
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_closed * 100) if total_closed > 0 else 0

        total_profit = sum(t.profit for t in wins)
        total_loss = sum(t.profit for t in losses)
        net_pnl = total_profit + total_loss
        roi = (self.balance - self.starting_balance) / self.starting_balance * 100

        avg_win = total_profit / win_count if win_count > 0 else 0
        avg_loss = total_loss / loss_count if loss_count > 0 else 0
        profit_factor = abs(total_profit / total_loss) if total_loss != 0 else float("inf")
        expectancy = (win_rate/100 * avg_win) + ((1-win_rate/100) * avg_loss) if total_closed > 0 else 0

        # Consecutive wins/losses
        max_consec_win, max_consec_loss = 0, 0
        cur_win, cur_loss = 0, 0
        for t in closed:
            if t.status == "WIN":
                cur_win += 1; cur_loss = 0
                max_consec_win = max(max_consec_win, cur_win)
            else:
                cur_loss += 1; cur_win = 0
                max_consec_loss = max(max_consec_loss, cur_loss)

        # Average hold time
        durations = []
        for t in closed:
            try:
                d = pd.Timestamp(t.exit_time) - pd.Timestamp(t.entry_time)
                durations.append(d.total_seconds() / 60)  # minutes
            except Exception:
                pass
        avg_hold = np.mean(durations) if durations else 0

        # Daily win rate consistency
        daily_wins = {}
        daily_totals = {}
        for t in closed:
            day = str(t.exit_time)[:10]
            daily_totals[day] = daily_totals.get(day, 0) + 1
            if t.status == "WIN":
                daily_wins[day] = daily_wins.get(day, 0) + 1
        profitable_days = sum(1 for d in self.daily_pnl.values() if d > 0)
        total_days = len(self.daily_pnl)

        print(f"""
{C.CY}{'═'*62}
  📊 BACKTEST REPORT
{'═'*62}{C.RST}

  {C.B}Performance Summary{C.RST}
  {'─'*50}
  Starting Balance:   ${self.starting_balance:>12,.2f}
  Final Balance:      ${self.balance:>12,.2f}
  Net P&L:           {C.G if net_pnl >= 0 else C.R}${net_pnl:>12,.2f}{C.RST}
  ROI:               {C.G if roi >= 0 else C.R}{roi:>12.2f}%{C.RST}
  Max Drawdown:      {C.R}{self.max_drawdown:>12.2f}%{C.RST}
  Total Fees:         ${self.total_fees:>12,.2f}

  {C.B}Trade Statistics{C.RST}
  {'─'*50}
  Total Trades:       {total_closed:>12}
  Wins:              {C.G}{win_count:>12}{C.RST}
  Losses:            {C.R}{loss_count:>12}{C.RST}
  Win Rate:          {C.G if win_rate >= 50 else C.R}{win_rate:>11.1f}%{C.RST}

  Avg Win:           {C.G}${avg_win:>12,.2f}{C.RST}
  Avg Loss:          {C.R}${avg_loss:>12,.2f}{C.RST}
  Profit Factor:      {profit_factor:>12.2f}
  Expectancy:        {C.G if expectancy >= 0 else C.R}${expectancy:>12,.2f}{C.RST}

  Max Consec Wins:    {max_consec_win:>12}
  Max Consec Losses:  {max_consec_loss:>12}
  Avg Hold Time:      {avg_hold:>9.0f} min

  {C.B}Daily Consistency{C.RST}
  {'─'*50}
  Trading Days:       {total_days:>12}
  Profitable Days:   {C.G}{profitable_days:>12}{C.RST}
  Losing Days:       {C.R}{total_days - profitable_days:>12}{C.RST}
  Day Win Rate:      {C.G if total_days > 0 and profitable_days/total_days >= 0.5 else C.R}{(profitable_days/total_days*100) if total_days > 0 else 0:>11.1f}%{C.RST}
""")

        # ── Exits breakdown ──
        reasons = {}
        for t in closed:
            reasons[t.reason] = reasons.get(t.reason, 0) + 1
        print(f"  {C.B}Exit Reasons{C.RST}")
        print(f"  {'─'*50}")
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            pct = count / total_closed * 100
            wins_for = sum(1 for t in closed if t.reason == reason and t.status == "WIN")
            print(f"  {reason:<20} {count:>4} ({pct:>5.1f}%)  WR: {wins_for/count*100:.0f}%")

        # ── Per-pair breakdown ──
        symbols = set(t.symbol for t in closed)
        if len(symbols) > 1:
            print(f"\n  {C.B}Per-Pair Results{C.RST}")
            print(f"  {'─'*50}")
            for sym in sorted(symbols):
                sym_trades = [t for t in closed if t.symbol == sym]
                sym_wins = sum(1 for t in sym_trades if t.status == "WIN")
                sym_pnl = sum(t.profit for t in sym_trades)
                sym_wr = sym_wins / len(sym_trades) * 100
                print(f"  {sym:<12} Trades: {len(sym_trades):>3} | WR: {sym_wr:>5.1f}% | P&L: ${sym_pnl:>8.2f}")

        # ── Daily P&L table ──
        if self.daily_pnl:
            print(f"\n  {C.B}Daily P&L{C.RST}")
            print(f"  {'─'*50}")
            for day, pnl in sorted(self.daily_pnl.items()):
                bar = "█" * min(30, int(abs(pnl) / 2))
                color = C.G if pnl >= 0 else C.R
                trades_today = daily_totals.get(day, 0)
                wr_today = daily_wins.get(day, 0) / trades_today * 100 if trades_today > 0 else 0
                print(f"  {day} │ {color}${pnl:>+8.2f}{C.RST} │ {trades_today} trades │ WR {wr_today:.0f}% │ {color}{bar}{C.RST}")

        # ── Top 5 best / worst trades ──
        if closed:
            by_profit = sorted(closed, key=lambda t: t.profit, reverse=True)
            print(f"\n  {C.B}Top 5 Best Trades{C.RST}")
            print(f"  {'─'*50}")
            for t in by_profit[:5]:
                print(f"  #{t.id:<4} {t.symbol:<10} {t.side:<5} "
                      f"${t.profit:>+8.2f} ({t.profit_pct:>+6.2f}%) {t.leverage}x | {t.reason}")

            print(f"\n  {C.B}Top 5 Worst Trades{C.RST}")
            print(f"  {'─'*50}")
            for t in by_profit[-5:]:
                print(f"  #{t.id:<4} {t.symbol:<10} {t.side:<5} "
                      f"${t.profit:>+8.2f} ({t.profit_pct:>+6.2f}%) {t.leverage}x | {t.reason}")

        # ── Equity curve (ASCII) ──
        if self.equity_curve:
            self._print_equity_chart()

        print(f"\n{C.CY}{'═'*62}{C.RST}\n")

    def _print_equity_chart(self):
        """Print ASCII equity curve."""
        equities = [e["equity"] for e in self.equity_curve]
        if not equities:
            return

        print(f"\n  {C.B}Equity Curve{C.RST}")
        print(f"  {'─'*55}")

        # Sample down to 50 points
        step = max(1, len(equities) // 50)
        sampled = equities[::step]
        min_eq = min(sampled)
        max_eq = max(sampled)
        eq_range = max_eq - min_eq if max_eq != min_eq else 1

        chart_height = 12
        chart_width = len(sampled)

        for row in range(chart_height, -1, -1):
            threshold = min_eq + (row / chart_height) * eq_range
            line = "  "
            if row == chart_height:
                line += f"${max_eq:>9,.0f} │"
            elif row == 0:
                line += f"${min_eq:>9,.0f} │"
            elif row == chart_height // 2:
                mid = (min_eq + max_eq) / 2
                line += f"${mid:>9,.0f} │"
            else:
                line += f"{'':>10} │"

            for val in sampled:
                if val >= threshold:
                    color = C.G if val >= self.starting_balance else C.R
                    line += f"{color}█{C.RST}"
                else:
                    line += " "
            print(line)

        print(f"  {'':>10} └{'─' * len(sampled)}")
        start_t = str(self.equity_curve[0]["timestamp"])[:10]
        end_t = str(self.equity_curve[-1]["timestamp"])[:10]
        print(f"  {'':>11}{start_t}{'':>{max(1, len(sampled) - 20)}}{end_t}")

    def export_csv(self, filename: str = "backtest_trades.csv"):
        """Export all trades to CSV."""
        rows = []
        for t in self.trades:
            rows.append({
                "id": t.id, "symbol": t.symbol, "side": t.side,
                "entry_price": t.entry_price, "exit_price": t.exit_price,
                "entry_time": t.entry_time, "exit_time": t.exit_time,
                "leverage": t.leverage, "margin": t.margin,
                "profit": round(t.profit, 4),
                "profit_pct": round(t.profit_pct, 2),
                "fee": round(t.fee, 4),
                "ta_score": t.ta_score, "confidence": t.confidence,
                "reason": t.reason, "status": t.status,
                "max_favorable": round(t.max_favorable, 2),
                "max_adverse": round(t.max_adverse, 2),
            })
        df = pd.DataFrame(rows)
        path = os.path.join(os.path.dirname(__file__), filename)
        df.to_csv(path, index=False)
        print(f"  📁 Trades exported to {path}")


# ─── CLI ───────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Futures Agent Backtester")
    parser.add_argument("--pair", type=str, default="BTC/USDT",
                        help="Single trading pair (default: BTC/USDT)")
    parser.add_argument("--pairs", type=str, default="",
                        help="Comma-separated pairs for multi-pair backtest")
    parser.add_argument("--days", type=int, default=7,
                        help="Number of days to backtest (default: 7)")
    parser.add_argument("--timeframe", type=str, default="5m",
                        help="Signal timeframe (default: 5m)")
    parser.add_argument("--balance", type=float, default=1000.0,
                        help="Starting balance in USDT (default: 1000)")
    parser.add_argument("--leverage", type=int, default=10,
                        help="Max leverage (default: 10)")
    parser.add_argument("--positions", type=int, default=3,
                        help="Max concurrent positions (default: 3)")
    parser.add_argument("--ai", action="store_true",
                        help="Enable AI confirmation (slower, uses Groq API)")
    parser.add_argument("--csv", action="store_true",
                        help="Export trades to CSV")
    args = parser.parse_args()

    print(f"""
{C.CY}╔══════════════════════════════════════════════════════════════╗
║  📊 FUTURES AGENT BACKTESTER                                 ║
╚══════════════════════════════════════════════════════════════╝{C.RST}
""")

    # Determine pairs
    if args.pairs:
        pairs = [p.strip() for p in args.pairs.split(",")]
    else:
        pairs = [args.pair]

    print(f"  Config:")
    print(f"  Pairs: {', '.join(pairs)}")
    print(f"  Period: {args.days} days")
    print(f"  Timeframe: {args.timeframe}")
    print(f"  Balance: ${args.balance:,.2f}")
    print(f"  Max Leverage: {args.leverage}x")
    print(f"  Max Positions: {args.positions}")
    print(f"  AI Mode: {'ON' if args.ai else 'OFF (TA-only)'}")
    print()

    # Download data
    pairs_data = {}
    for symbol in pairs:
        df = download_candles(symbol, args.timeframe, args.days)
        if not df.empty:
            pairs_data[symbol] = df

    if not pairs_data:
        print(f"\n  {C.R}No data downloaded. Check internet or Binance API access.{C.RST}")
        sys.exit(1)

    # Run backtest
    bt = Backtester(
        starting_balance=args.balance,
        max_leverage=args.leverage,
        max_positions=args.positions,
        use_ai=args.ai,
        signal_timeframe=args.timeframe,
    )

    start = time.time()

    if len(pairs_data) == 1:
        symbol = list(pairs_data.keys())[0]
        bt.run(pairs_data[symbol], symbol)
    else:
        bt.run_multi(pairs_data)

    elapsed = time.time() - start
    print(f"\n  ⏱ Backtest completed in {elapsed:.1f}s")

    # Report
    bt.report()

    # Export CSV
    if args.csv:
        bt.export_csv()

    return bt


if __name__ == "__main__":
    main()
