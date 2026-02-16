"""
Aggressive Futures Trading Engine — Small Account Growth Mode
================================================================
Designed for $50-$100 accounts targeting maximum growth.

Strategy:
1. Telegram signal scraping (follow high-WR channels)
2. TA confirmation before entry (reject bad signals)
3. High leverage (10-20x) with TIGHT stop losses
4. Compound gains (reinvest profits every trade)
5. Scalping mode for quick entries/exits
6. Multiple TP levels with partial closes

Risk warning: This is HIGH RISK. Only use money you can afford to lose.

Usage:
    python run_aggressive.py [--reset] [--balance 50] [--no-ta]

Telegram commands:
    /signal LONG BTC 69000 TP 71000 SL 68000 20x
    /add_channel @channel_name
    /channels
    /balance
    /positions
    /stats
    /aggressive_mode on|off
"""

import os
import sys
import json
import time
import signal
import logging
import argparse
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

# ─── Logging ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
_fh = logging.FileHandler("aggressive_debug.log", mode="a")
_fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-5s | %(message)s", datefmt="%H:%M:%S"))
logging.getLogger().addHandler(_fh)
logging.getLogger("ccxt").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logger = logging.getLogger("aggressive")


# ─── Telegram Helper ──────────────────────────────────
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def tg_send(msg: str):
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": CHAT_ID, "text": msg,
            "parse_mode": "HTML",
        }, timeout=5)
    except Exception:
        pass


# ─── Config ────────────────────────────────────────────
TRADING_PAIRS = os.getenv("TRADING_PAIRS", "BTC/USDT,ETH/USDT,SOL/USDT").split(",")
SCAN_INTERVAL = 30  # Faster scanning for aggressive mode


class AggressiveTrader:
    """
    Aggressive trading engine for small accounts.
    Combines: signal scraping + TA confirmation + high leverage.
    """

    def __init__(self, starting_balance: float = 50.0, use_ta: bool = True):
        from market_data import MarketData
        from technical import TechnicalAnalyzer
        from trade_db import TradeDB
        from signal_scraper import TelegramSignalScraper
        from chart_analyzer import ChartAnalyzer
        from telegram_reader import TelegramChannelReader

        self.market = MarketData()
        self.ta = TechnicalAnalyzer()
        self.db = TradeDB("aggressive_trades.db", starting_balance)
        self.scraper = TelegramSignalScraper()
        self.analyzer = ChartAnalyzer()
        self.channel_reader = TelegramChannelReader()
        self.use_ta = use_ta

        # News context (updated each cycle)
        self.news_context = {"sentiment": "NEUTRAL", "events": []}

        # Aggressive settings
        self.default_leverage = 15
        self.max_leverage = 20
        self.max_positions = 3
        self.risk_per_trade = 0.10  # 10% risk per trade (aggressive)
        self.margin_per_trade = 0.40  # Max 40% margin per trade

        # State
        self.state_file = "aggressive_state.json"
        self.cycle = 0
        self.start_time = None
        self.running = True
        self.consecutive_losses = 0
        self.peak_balance = starting_balance

        self._load_state()

        signal.signal(signal.SIGINT, lambda *_: setattr(self, 'running', False))
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, 'running', False))

    def _load_state(self):
        try:
            with open(self.state_file, "r") as f:
                state = json.load(f)
                self.start_time = datetime.fromisoformat(state["start_time"])
                self.cycle = state.get("cycle", 0)
                self.consecutive_losses = state.get("consecutive_losses", 0)
                self.peak_balance = state.get("peak_balance", self.db.balance)
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            self.start_time = datetime.now()

    def _save_state(self):
        with open(self.state_file, "w") as f:
            json.dump({
                "start_time": self.start_time.isoformat(),
                "cycle": self.cycle,
                "consecutive_losses": self.consecutive_losses,
                "peak_balance": self.peak_balance,
            }, f, indent=2)

    def run(self):
        """Main trading loop."""
        logger.info(f"AGGRESSIVE MODE STARTED")
        logger.info(f"Balance: ${self.db.balance:.2f}")
        logger.info(f"Default leverage: {self.default_leverage}x")
        logger.info(f"Max leverage: {self.max_leverage}x")
        logger.info(f"Risk per trade: {self.risk_per_trade*100:.0f}%")
        logger.info(f"TA confirmation: {'ON' if self.use_ta else 'OFF'}")

        tg_send(
            f"🔥 <b>AGGRESSIVE MODE STARTED</b>\n"
            f"Balance: ${self.db.balance:.2f}\n"
            f"Leverage: {self.default_leverage}x (max {self.max_leverage}x)\n"
            f"Risk/trade: {self.risk_per_trade*100:.0f}%\n"
            f"TA: {'ON' if self.use_ta else 'OFF'}\n"
            f"Send /signal to add manual signals"
        )

        while self.running:
            try:
                self.cycle += 1
                self._run_cycle()
                self._save_state()
                self._print_dashboard()

                # Sleep with position monitoring
                self._sleep_with_monitoring(SCAN_INTERVAL)

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Cycle error: {e}")
                time.sleep(10)

        logger.info("Aggressive trader stopped.")
        self._print_final_report()

    def _run_cycle(self):
        """One trading cycle."""
        open_positions = self.db.get_open_trades()

        # 1. Monitor existing positions
        if open_positions:
            self._monitor_positions(open_positions)

        # 2. Check if we can open new trades
        open_count = len(self.db.get_open_trades())
        if open_count >= self.max_positions:
            return

        # 3. Loss streak protection
        if self.consecutive_losses >= 4:
            logger.info(f"Loss streak: {self.consecutive_losses}. Skipping 1 cycle to cool down.")
            self.consecutive_losses = 3  # Reset partially
            return

        # 4. Read Telegram channels (AI analysis — highest priority)
        if self.channel_reader.is_configured():
            channel_signals = self._process_channel_messages()
            for sig in channel_signals:
                if open_count >= self.max_positions:
                    break
                if self._execute_signal(sig):
                    open_count += 1

        # 5. Check for manual Telegram signals (/signal command)
        pending_signals = self.scraper.get_pending_signals()
        for sig in pending_signals:
            if open_count >= self.max_positions:
                break
            if self._execute_signal(sig):
                open_count += 1
                self.scraper.mark_executed(sig)
            else:
                self.scraper.mark_skipped(sig, "Failed validation")

        # 6. TA-based scanning (if still have slots)
        if open_count < self.max_positions:
            for symbol in TRADING_PAIRS:
                if open_count >= self.max_positions:
                    break
                if any(t["symbol"] == symbol for t in self.db.get_open_trades()):
                    continue
                if self._ta_scan_and_trade(symbol):
                    open_count += 1

    def _process_channel_messages(self) -> List[Dict]:
        """Read and analyze Telegram channel messages."""
        signals = []
        news_messages = []

        try:
            messages = self.channel_reader.fetch_sync()
            if not messages:
                return signals

            logger.info(f"Processing {len(messages)} channel messages")

            for msg in messages:
                # Analyze with AI (text + image)
                result = self.analyzer.analyze_message(msg)
                if not result:
                    continue

                # Separate signals from news
                if result.get("is_news"):
                    news_messages.append(msg)
                    continue

                if result.get("side") and result.get("pair"):
                    # Filter: only high-confidence signals
                    conf = result.get("confidence", 0)
                    if conf >= 0.55:
                        signals.append(result)
                        logger.info(
                            f"  Channel signal: {result['side']} {result['pair']} "
                            f"conf={conf:.0%} src={msg.get('channel', '?')}"
                        )

            # Update news context
            if news_messages:
                self.news_context = self.analyzer.analyze_news_context(news_messages)
                sentiment = self.news_context.get("sentiment", "NEUTRAL")
                logger.info(f"  News sentiment: {sentiment}")

        except Exception as e:
            logger.error(f"Channel processing error: {e}")

        return signals

    def _execute_signal(self, signal_data: Dict) -> bool:
        """Execute a parsed Telegram signal."""
        pair = signal_data["pair"]
        side = signal_data["side"]
        entry = signal_data.get("entry")
        targets = signal_data.get("targets", [])
        sl = signal_data.get("stop_loss")
        sig_leverage = signal_data.get("leverage")

        logger.info(f"Processing signal: {side} {pair}")

        # News sentiment boost/penalty
        news_sentiment = self.news_context.get("sentiment", "NEUTRAL")
        news_boost = 1.0
        if news_sentiment == "BULLISH" and side == "LONG":
            news_boost = 1.15
        elif news_sentiment == "BEARISH" and side == "SHORT":
            news_boost = 1.15
        elif news_sentiment == "BULLISH" and side == "SHORT":
            news_boost = 0.85
        elif news_sentiment == "BEARISH" and side == "LONG":
            news_boost = 0.85

        # Get current price
        price = self.market.get_current_price(pair)
        if not price:
            logger.info(f"  {pair}: No price available")
            return False

        # If entry is specified, check if current price is close enough
        if entry:
            entry_diff_pct = abs(price - entry) / entry * 100
            if entry_diff_pct > 2.0:
                logger.info(f"  {pair}: Price ${price:,.2f} too far from entry ${entry:,.2f} ({entry_diff_pct:.1f}%)")
                return False

        # TA confirmation (optional but recommended)
        ta_agrees = True
        ta_score = 50
        if self.use_ta:
            ta_agrees, ta_score = self._ta_confirmation(pair, side)
            if not ta_agrees:
                logger.info(f"  {pair}: TA disagrees (score={ta_score:.0f})")
                return False

        # Calculate SL if not provided
        if not sl:
            candles_5m = self.market.get_candles(pair, "5m", 50)
            if not candles_5m.empty:
                from technical import atr as calc_atr
                atr_val = calc_atr(candles_5m["high"], candles_5m["low"], candles_5m["close"], 14).iloc[-1]
            else:
                atr_val = price * 0.01
            sl_distance = atr_val * 1.5
            sl = price - sl_distance if side == "LONG" else price + sl_distance

        # Calculate levels
        sl_dist_pct = abs(price - sl) / price * 100

        # Set TP levels if not provided
        if not targets:
            sl_dist = abs(price - sl)
            if side == "LONG":
                targets = [price + sl_dist * 1.5, price + sl_dist * 2.5, price + sl_dist * 4]
            else:
                targets = [price - sl_dist * 1.5, price - sl_dist * 2.5, price - sl_dist * 4]

        # Determine leverage
        leverage = sig_leverage or self._calc_aggressive_leverage(sl_dist_pct, ta_score)

        # Position sizing
        pos = self._calc_position(price, sl_dist_pct, leverage)
        if not pos:
            return False

        # Build trade
        tp1 = targets[0] if len(targets) > 0 else (price * 1.02 if side == "LONG" else price * 0.98)
        tp2 = targets[1] if len(targets) > 1 else (price * 1.04 if side == "LONG" else price * 0.96)
        tp3 = targets[2] if len(targets) > 2 else (price * 1.06 if side == "LONG" else price * 0.94)

        trade = {
            "symbol": pair, "side": side, "action": side,
            "entry_price": price, "quantity": pos["quantity"],
            "leverage": leverage, "margin": pos["margin"],
            "position_value": pos["value"],
            "stop_loss": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
            "sl_pct": sl_dist_pct,
            "confidence": min(0.95, ta_score / 100) if side == "LONG" else min(0.95, (100 - ta_score) / 100),
            "reasoning": f"Signal: {signal_data.get('source', '?')} | TA score={ta_score:.0f}",
            "model": "SIGNAL" + ("+TA" if self.use_ta else ""),
            "ta_score": ta_score,
        }

        result = self.db.open_trade(trade)
        trade_id = result.get("id") if isinstance(result, dict) else result
        if trade_id:
            logger.info(f"  OPENED #{trade_id}: {side} {pair} @ ${price:,.2f} | {leverage}x | margin ${pos['margin']:.2f}")
            tg_send(
                f"📊 <b>SIGNAL TRADE OPENED</b>\n"
                f"{side} {pair} @ ${price:,.4f}\n"
                f"Leverage: {leverage}x\n"
                f"SL: ${sl:,.4f} ({sl_dist_pct:.2f}%)\n"
                f"TP1: ${tp1:,.4f}\n"
                f"Margin: ${pos['margin']:.2f}\n"
                f"Source: {signal_data.get('source', 'manual')}"
            )
            return True

        return False

    def _ta_scan_and_trade(self, symbol: str) -> bool:
        """Scan pair with TA and open trade if strong signal."""
        candles = self.market.get_multi_timeframe(symbol)
        if len(candles) < 2:
            return False

        result = self.ta.multi_timeframe_analysis(candles)
        consensus = result.get("consensus", "SKIP")
        score = result.get("consensus_score", 50)

        # Accept both consensus and individual TF signals
        if consensus == "SKIP":
            tf_data = result.get("timeframes", {})
            best_signal = None
            best_score = 0
            for tf in ["4h", "1h", "15m", "5m"]:
                if tf in tf_data:
                    s = tf_data[tf].get("score", 50)
                    sig = tf_data[tf].get("signal", "SKIP")
                    if sig != "SKIP" and (s >= 68 or s <= 32):
                        discount = {"4h": 0.92, "1h": 0.88, "15m": 0.82, "5m": 0.78}
                        adj = s * discount.get(tf, 0.80)
                        if adj > best_score:
                            best_signal = sig
                            best_score = adj
            if best_signal:
                consensus = best_signal
                score = best_score
            else:
                return False

        side = consensus
        confidence = min(0.95, score / 100) if side == "LONG" else min(0.95, (100 - score) / 100)

        if confidence < 0.58:
            return False

        price = self.market.get_current_price(symbol)
        if not price:
            return False

        # Calculate SL/TP
        tf_5m = result.get("timeframes", {}).get("5m", {})
        atr_val = tf_5m.get("atr", price * 0.01)
        levels = self.ta.calculate_sl_tp(price, side, atr_val)
        sl_dist_pct = levels["sl_distance_pct"]

        # Aggressive leverage
        leverage = self._calc_aggressive_leverage(sl_dist_pct, score)

        # Position sizing
        pos = self._calc_position(price, sl_dist_pct, leverage)
        if not pos:
            return False

        trade = {
            "symbol": symbol, "side": side, "action": side,
            "entry_price": price, "quantity": pos["quantity"],
            "leverage": leverage, "margin": pos["margin"],
            "position_value": pos["value"],
            "stop_loss": levels["stop_loss"],
            "tp1": levels["tp1"], "tp2": levels["tp2"], "tp3": levels["tp3"],
            "sl_pct": sl_dist_pct, "confidence": confidence,
            "reasoning": f"TA aggressive score={score:.1f}",
            "model": "TA_AGG",
            "ta_score": score,
        }

        result = self.db.open_trade(trade)
        trade_id = result.get("id") if isinstance(result, dict) else result
        if trade_id:
            logger.info(f"  OPENED #{trade_id}: {side} {symbol} @ ${price:,.2f} | {leverage}x | margin ${pos['margin']:.2f}")
            tg_send(
                f"📊 <b>TA TRADE OPENED</b>\n"
                f"{side} {symbol} @ ${price:,.4f}\n"
                f"Leverage: {leverage}x | Score: {score:.0f}\n"
                f"SL: ${levels['stop_loss']:,.4f} ({sl_dist_pct:.2f}%)\n"
                f"TP1: ${levels['tp1']:,.4f}\n"
                f"Margin: ${pos['margin']:.2f}"
            )
            return True
        return False

    def _ta_confirmation(self, pair: str, side: str) -> tuple:
        """Check if TA agrees with signal direction. Returns (agrees, score)."""
        candles = self.market.get_multi_timeframe(pair)
        if len(candles) < 1:
            return True, 50  # No data = allow signal through

        result = self.ta.multi_timeframe_analysis(candles)
        score = result.get("consensus_score", 50)

        # For LONG: score > 45 is OK (just not strongly short)
        # For SHORT: score < 55 is OK (just not strongly long)
        if side == "LONG":
            return score >= 45, score
        else:
            return score <= 55, score

    def _calc_aggressive_leverage(self, sl_dist_pct: float, ta_score: float) -> int:
        """Calculate leverage aggressively but with SL-based limits."""
        # Core idea: leverage * SL% should not exceed 30% of margin
        # So if SL = 0.5%, max leverage = 30% / 0.5% = 60x
        # But we cap much lower for safety

        # Score-based base leverage
        strength = abs(ta_score - 50) / 50  # 0 to 1
        if strength > 0.6:
            base = 20
        elif strength > 0.4:
            base = 15
        elif strength > 0.2:
            base = 10
        else:
            base = 8

        # SL-based safety cap: leverage * SL < 25% max loss per trade
        safety_max = int(25 / max(sl_dist_pct, 0.1))

        leverage = min(base, safety_max, self.max_leverage)
        return max(2, leverage)

    def _calc_position(self, price: float, sl_dist_pct: float,
                       leverage: int) -> Optional[Dict]:
        """Calculate position size for aggressive mode."""
        balance = self.db.balance

        # Risk amount: 10% of balance per trade
        risk_amount = balance * self.risk_per_trade

        # Position value based on risk
        if sl_dist_pct > 0:
            position_value = risk_amount / (sl_dist_pct / 100)
        else:
            position_value = risk_amount * 10

        # Cap by leverage
        max_position = balance * leverage
        position_value = min(position_value, max_position)

        # Margin required
        margin = position_value / leverage

        # Cap margin at % of balance
        if margin > balance * self.margin_per_trade:
            margin = balance * self.margin_per_trade
            position_value = margin * leverage

        quantity = position_value / price

        if margin < 1 or margin > balance:
            logger.info(f"  Position too small/large: margin=${margin:.2f} balance=${balance:.2f}")
            return None

        return {
            "margin": round(margin, 2),
            "value": round(position_value, 2),
            "quantity": round(quantity, 6),
        }

    def _monitor_positions(self, positions: List[Dict]):
        """Monitor open positions for SL/TP hits."""
        for trade in positions:
            try:
                price = self.market.get_current_price(trade["symbol"])
                if not price:
                    continue

                side = trade["side"]
                entry = trade["entry_price"]
                sl = trade["stop_loss"]
                tp1 = trade["tp1"]
                tp2 = trade.get("tp2", tp1 * 1.02 if side == "LONG" else tp1 * 0.98)
                tp3 = trade.get("tp3", tp2 * 1.02 if side == "LONG" else tp2 * 0.98)

                # Calculate current P&L
                if side == "LONG":
                    pnl_pct = (price - entry) / entry * 100
                    hit_sl = price <= sl
                    hit_tp1 = price >= tp1
                    hit_tp2 = price >= tp2
                    hit_tp3 = price >= tp3
                else:
                    pnl_pct = (entry - price) / entry * 100
                    hit_sl = price >= sl
                    hit_tp1 = price <= tp1
                    hit_tp2 = price <= tp2
                    hit_tp3 = price <= tp3

                leveraged_pnl = pnl_pct * trade["leverage"]

                # Check TP3 (close 100%)
                if hit_tp3:
                    self._close_trade(trade, price, "TP3", leveraged_pnl)
                    continue

                # Check TP2 (close 50% virtually — just move SL to entry)
                if hit_tp2:
                    # Move SL to breakeven + small profit
                    new_sl = entry * (1.002 if side == "LONG" else 0.998)
                    if (side == "LONG" and new_sl > sl) or (side == "SHORT" and new_sl < sl):
                        self.db.update_stop_loss(trade["id"], new_sl)
                        logger.info(f"  #{trade['id']} {trade['symbol']}: TP2 hit, SL → breakeven ${new_sl:,.4f}")
                    continue

                # Check TP1 (move SL to entry = risk-free)
                if hit_tp1:
                    new_sl = entry
                    if (side == "LONG" and new_sl > sl) or (side == "SHORT" and new_sl < sl):
                        self.db.update_stop_loss(trade["id"], new_sl)
                        logger.info(f"  #{trade['id']} {trade['symbol']}: TP1 hit, SL → entry ${entry:,.4f}")
                    continue

                # Check SL
                if hit_sl:
                    self._close_trade(trade, price, "SL", leveraged_pnl)
                    continue

                # Emergency: if leveraged loss > 20%, force close
                if leveraged_pnl < -20:
                    self._close_trade(trade, price, "EMERGENCY_SL", leveraged_pnl)
                    continue

            except Exception as e:
                logger.error(f"Monitor error #{trade['id']}: {e}")

    def _close_trade(self, trade: Dict, price: float, reason: str, pnl_pct: float):
        """Close a trade and update stats."""
        result = self.db.close_trade(trade["id"], price, reason)
        profit = result.get("profit", 0)

        if profit >= 0:
            self.consecutive_losses = 0
            self.peak_balance = max(self.peak_balance, self.db.balance)
        else:
            self.consecutive_losses += 1

        emoji = "✅" if profit >= 0 else "❌"
        logger.info(f"  CLOSED #{trade['id']}: {trade['side']} {trade['symbol']} | {reason} | P&L: ${profit:+.2f} ({pnl_pct:+.1f}%)")
        tg_send(
            f"{emoji} <b>TRADE CLOSED</b>\n"
            f"{trade['side']} {trade['symbol']} @ ${price:,.4f}\n"
            f"Reason: {reason}\n"
            f"P&L: ${profit:+.2f} ({pnl_pct:+.1f}%)\n"
            f"Balance: ${self.db.balance:.2f}"
        )

    def _sleep_with_monitoring(self, seconds: int):
        """Sleep but check SL every 10 seconds."""
        for _ in range(seconds // 10):
            if not self.running:
                return
            time.sleep(10)
            # Quick SL check
            for trade in self.db.get_open_trades():
                try:
                    price = self.market.get_current_price(trade["symbol"])
                    if not price:
                        continue
                    side = trade["side"]
                    sl = trade["stop_loss"]
                    entry = trade["entry_price"]
                    if side == "LONG":
                        pnl_pct = (price - entry) / entry * 100 * trade["leverage"]
                        if price <= sl:
                            self._close_trade(trade, price, "SL", pnl_pct)
                    else:
                        pnl_pct = (entry - price) / entry * 100 * trade["leverage"]
                        if price >= sl:
                            self._close_trade(trade, price, "SL", pnl_pct)
                    # Emergency SL
                    if pnl_pct < -20:
                        self._close_trade(trade, price, "EMERGENCY_SL", pnl_pct)
                except Exception:
                    pass

    def _print_dashboard(self):
        """Print compact dashboard to terminal."""
        stats = self.db.get_stats()
        open_trades = self.db.get_open_trades()
        elapsed = datetime.now() - self.start_time
        hours = elapsed.total_seconds() / 3600

        print(f"\033[2J\033[H", end="")
        print("=" * 60)
        print(f"  🔥 AGGRESSIVE TRADER | Cycle #{self.cycle}")
        print(f"  Running: {hours:.1f}h | Pairs: {len(TRADING_PAIRS)}")
        print("=" * 60)
        print(f"  Balance:  ${stats['balance']:>10.2f}  (start: ${stats['starting_balance']:.2f})")

        roi = (stats['balance'] - stats['starting_balance']) / stats['starting_balance'] * 100
        roi_color = "\033[92m" if roi >= 0 else "\033[91m"
        print(f"  ROI:      {roi_color}{roi:>+10.2f}%\033[0m")
        print(f"  PnL:      ${stats['total_pnl']:>+10.2f}")
        print(f"  Trades:   {stats['total_trades']:>10} (W:{stats['wins']} L:{stats['losses']})")
        print(f"  Win Rate: {stats['win_rate']:>10.1f}%")
        print(f"  Open:     {stats['open_positions']:>10}")
        print(f"  Streak:   {'🔥' * max(0, 3-self.consecutive_losses)}{'💀' * self.consecutive_losses}")
        print("-" * 60)

        if open_trades:
            for t in open_trades:
                price = self.market.get_current_price(t["symbol"])
                if price:
                    if t["side"] == "LONG":
                        pnl = (price - t["entry_price"]) / t["entry_price"] * 100 * t["leverage"]
                    else:
                        pnl = (t["entry_price"] - price) / t["entry_price"] * 100 * t["leverage"]
                    color = "\033[92m" if pnl >= 0 else "\033[91m"
                    print(f"  #{t['id']} {t['side']:5} {t['symbol']:10} {t['leverage']:2}x | {color}{pnl:+.2f}%\033[0m")

        print("=" * 60)

    def _print_final_report(self):
        """Print final report when stopping."""
        stats = self.db.get_stats()
        elapsed = datetime.now() - self.start_time
        roi = (stats['balance'] - stats['starting_balance']) / stats['starting_balance'] * 100

        report = (
            f"\n{'='*50}\n"
            f"  AGGRESSIVE TRADER — FINAL REPORT\n"
            f"{'='*50}\n"
            f"  Duration:     {elapsed}\n"
            f"  Start:        ${stats['starting_balance']:.2f}\n"
            f"  Final:        ${stats['balance']:.2f}\n"
            f"  ROI:          {roi:+.2f}%\n"
            f"  Total PnL:    ${stats['total_pnl']:+.2f}\n"
            f"  Trades:       {stats['total_trades']}\n"
            f"  Win Rate:     {stats['win_rate']:.1f}%\n"
            f"  Peak Balance: ${self.peak_balance:.2f}\n"
            f"{'='*50}\n"
        )
        print(report)
        logger.info(report)
        tg_send(
            f"📊 <b>FINAL REPORT</b>\n"
            f"Balance: ${stats['starting_balance']:.2f} → ${stats['balance']:.2f}\n"
            f"ROI: {roi:+.2f}%\n"
            f"Trades: {stats['total_trades']} | WR: {stats['win_rate']:.1f}%\n"
            f"Duration: {elapsed}"
        )


# ─── Main ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Aggressive Futures Trader")
    parser.add_argument("--reset", action="store_true", help="Reset state and DB")
    parser.add_argument("--balance", type=float, default=50.0, help="Starting balance (default: $50)")
    parser.add_argument("--no-ta", action="store_true", help="Disable TA confirmation")
    parser.add_argument("--leverage", type=int, default=15, help="Default leverage (default: 15)")
    parser.add_argument("--max-leverage", type=int, default=20, help="Max leverage (default: 20)")
    parser.add_argument("--status", action="store_true", help="Show current status and exit")
    args = parser.parse_args()

    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    if args.reset:
        import glob
        for f in ["aggressive_trades.db", "aggressive_state.json",
                   "aggressive_debug.log", "signals_history.json"]:
            try:
                os.remove(f)
            except FileNotFoundError:
                pass
        print("Reset complete.")

    if args.status:
        try:
            from trade_db import TradeDB
            db = TradeDB("aggressive_trades.db", args.balance)
            stats = db.get_stats()
            roi = (stats['balance'] - stats['starting_balance']) / stats['starting_balance'] * 100
            print(f"Balance: ${stats['balance']:.2f} | ROI: {roi:+.2f}%")
            print(f"Trades: {stats['total_trades']} | WR: {stats['win_rate']:.1f}%")
            print(f"Open: {stats['open_positions']} | PnL: ${stats['total_pnl']:+.2f}")
            for t in db.get_open_trades():
                print(f"  #{t['id']} {t['side']} {t['symbol']} @ ${t['entry_price']:,.4f}")
        except Exception as e:
            print(f"No data: {e}")
        return

    trader = AggressiveTrader(
        starting_balance=args.balance,
        use_ta=not args.no_ta,
    )
    trader.default_leverage = args.leverage
    trader.max_leverage = args.max_leverage
    trader.run()


if __name__ == "__main__":
    main()
