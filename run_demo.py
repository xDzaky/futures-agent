"""
7-Day Demo Trading — Paper Trading Simulator
===============================================
Runs the full TA + AI pipeline with LIVE market data but
FAKE money. Designed to run for exactly 7 days non-stop.

Features:
- Live price feeds from CryptoCompare/CoinGecko
- Full multi-timeframe TA (5m, 15m, 1h, 4h)
- AI trade confirmation via Groq (optional)
- SL/TP monitoring every 30 seconds
- SQLite persistence (survives restarts)
- Daily summary via Telegram
- Auto-stops after 7 days
- Resume support (just run again to continue)

Usage:
  python run_demo.py                  # Start 7-day demo
  python run_demo.py --reset          # Reset and start fresh
  python run_demo.py --status         # Show current status
  python run_demo.py --no-ai          # TA-only (no Groq calls)
"""

import os
import sys
import time
import json
import logging
import argparse
import threading
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

from market_data import MarketData
from technical import TechnicalAnalyzer
from risk_manager import RiskManager
from trade_db import TradeDB
from news_feeds import NewsFeedManager

load_dotenv()

# ─── Config ────────────────────────────────────────────
DEMO_DURATION_DAYS = 7
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL_SECONDS", "60"))
TRADING_PAIRS = os.getenv(
    "TRADING_PAIRS", "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT"
).split(",")
STARTING_BALANCE = float(os.getenv("STARTING_BALANCE", "1000.0"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

DB_PATH = os.path.join(os.path.dirname(__file__), "demo_trades.db")
STATE_FILE = os.path.join(os.path.dirname(__file__), "demo_state.json")


# ─── Colors ────────────────────────────────────────────
class C:
    G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; CY = "\033[96m"
    M = "\033[95m"; B = "\033[1m"; D = "\033[2m"; RST = "\033[0m"


# ─── Logging ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
# Also log to file so dashboard escape codes don't eat output
_fh = logging.FileHandler("demo_debug.log", mode="a")
_fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-5s | %(message)s", datefmt="%H:%M:%S"))
logging.getLogger().addHandler(_fh)
logging.getLogger("ccxt").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logger = logging.getLogger("demo")


# ─── Telegram Helper ──────────────────────────────────
def tg_send(msg: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


# ─── Telegram Bot (background) ────────────────────────
class DemoTelegramBot:
    """Handles /commands in background thread."""

    def __init__(self, db: TradeDB):
        self.db = db
        self.token = TELEGRAM_BOT_TOKEN
        self.offset = 0
        self.running = False

    def start(self):
        if not self.token:
            return
        self.running = True
        t = threading.Thread(target=self._poll, daemon=True)
        t.start()

    def _poll(self):
        while self.running:
            try:
                url = f"https://api.telegram.org/bot{self.token}/getUpdates"
                r = requests.get(url, params={"offset": self.offset, "timeout": 30}, timeout=35)
                if r.status_code == 200:
                    for u in r.json().get("result", []):
                        self.offset = u["update_id"] + 1
                        self._handle(u)
            except Exception:
                time.sleep(5)

    def _handle(self, update):
        msg = update.get("message", {})
        text = msg.get("text", "").strip()
        chat_id = msg.get("chat", {}).get("id")
        if not text or not chat_id:
            return

        reply = ""
        if text == "/balance":
            s = self.db.get_stats()
            reply = (
                f"<b>Demo Balance</b>\n"
                f"Balance: ${s['balance']:.2f}\n"
                f"P&L: ${s['total_pnl']:.2f}\n"
                f"ROI: {s['roi']:.1f}%\n"
                f"Trades: {s['total_trades']} (WR: {s['win_rate']:.1f}%)"
            )
        elif text == "/positions":
            pos = self.db.get_open_trades()
            if not pos:
                reply = "No open positions."
            else:
                lines = ["<b>Open Positions</b>"]
                for p in pos:
                    icon = "L" if p["side"] == "LONG" else "S"
                    lines.append(f"{icon} {p['symbol']} {p['leverage']}x @ ${p['entry_price']:,.2f}")
                reply = "\n".join(lines)
        elif text == "/stats":
            s = self.db.get_stats()
            reply = (
                f"<b>Demo Stats</b>\n"
                f"Wins: {s['wins']} | Losses: {s['losses']}\n"
                f"Win Rate: {s['win_rate']:.1f}%\n"
                f"ROI: {s['roi']:.1f}%\n"
                f"Fees: ${s['total_fees']:.4f}"
            )
        elif text in ("/start", "/help"):
            reply = (
                "<b>Demo Trading Bot</b>\n\n"
                "/balance - Current balance\n"
                "/positions - Open positions\n"
                "/stats - Win rate & stats\n"
                "/trades - Recent trades"
            )
        elif text == "/trades":
            trades = self.db.get_closed_trades(limit=5)
            if not trades:
                reply = "No closed trades yet."
            else:
                lines = ["<b>Recent Trades</b>"]
                for t in trades:
                    icon = "W" if t["profit"] > 0 else "L"
                    lines.append(f"{icon} {t['symbol']} {t['side']} ${t['profit']:.2f} ({t['close_reason']})")
                reply = "\n".join(lines)

        if reply:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    json={"chat_id": chat_id, "text": reply, "parse_mode": "HTML"},
                    timeout=10,
                )
            except Exception:
                pass


# ─── Demo State (persist across restarts) ─────────────
def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ─── Main Demo Runner ─────────────────────────────────
class DemoRunner:
    """7-day paper trading demo."""

    def __init__(self, use_ai: bool = True):
        self.market = MarketData()
        self.ta = TechnicalAnalyzer()
        self.risk = RiskManager()
        self.news = NewsFeedManager()
        self.db = TradeDB(DB_PATH, STARTING_BALANCE)
        self.use_ai = use_ai
        self.ai = None
        self.consecutive_losses = 0

        if use_ai:
            try:
                from ai_analyzer import AIAnalyzer
                self.ai = AIAnalyzer()
                logger.info("AI enabled (Groq Llama 3.3 70B)")
            except Exception as e:
                logger.warning(f"AI disabled: {e}")
                self.use_ai = False

        # Load or create state
        self.state = load_state()
        if "start_time" not in self.state:
            self.state["start_time"] = datetime.now().isoformat()
            self.state["cycle"] = 0
            self.state["last_daily_summary"] = ""
            save_state(self.state)

        self.start_time = datetime.fromisoformat(self.state["start_time"])
        self.cycle = self.state.get("cycle", 0)

        # Telegram bot
        self.bot = DemoTelegramBot(self.db)

    @property
    def elapsed_days(self) -> float:
        return (datetime.now() - self.start_time).total_seconds() / 86400

    @property
    def remaining(self) -> str:
        left = timedelta(days=DEMO_DURATION_DAYS) - (datetime.now() - self.start_time)
        if left.total_seconds() <= 0:
            return "DONE"
        d = left.days
        h, rem = divmod(left.seconds, 3600)
        m = rem // 60
        return f"{d}d {h}h {m}m"

    def run(self):
        """Main loop — runs for 7 days then stops."""
        self._print_banner()
        self.bot.start()

        # Send startup notification
        tg_send(
            f"<b>Demo Trading Started</b>\n"
            f"Balance: ${self.db.balance:.2f}\n"
            f"Pairs: {len(TRADING_PAIRS)}\n"
            f"Duration: {DEMO_DURATION_DAYS} days\n"
            f"AI: {'ON' if self.use_ai else 'OFF'}"
        )

        try:
            while self.elapsed_days < DEMO_DURATION_DAYS:
                self.cycle += 1
                self.state["cycle"] = self.cycle
                save_state(self.state)

                self._render_dashboard()
                self._run_cycle()
                self._check_daily_summary()

                # Sleep with SL monitoring
                self._sleep_monitor(SCAN_INTERVAL)

        except KeyboardInterrupt:
            logger.info("Stopped by user (Ctrl+C). Resume anytime with: python run_demo.py")
            tg_send("Demo paused by user. Resume with: python run_demo.py")

        # Final report
        if self.elapsed_days >= DEMO_DURATION_DAYS:
            self._final_report()

    def _run_cycle(self):
        """One scan cycle across all pairs."""
        stats = self.db.get_stats()
        open_count = stats["open_positions"]

        # Pre-trade safety
        check = self.risk.check_can_trade(self.db.balance, open_count, self.db.daily_pnl)

        # Always monitor open positions
        self._monitor_positions()

        if not check["can_trade"]:
            logger.info(f"Skip trading: {check['reason']}")
            return

        # Scan each pair
        for symbol in TRADING_PAIRS:
            symbol = symbol.strip()
            if not symbol:
                continue
            if self.db.is_symbol_open(symbol):
                continue
            if open_count >= int(os.getenv("MAX_OPEN_POSITIONS", "3")):
                break

            try:
                traded = self._analyze_and_trade(symbol)
                if traded:
                    open_count += 1
            except Exception as e:
                logger.error(f"{symbol} error: {e}")

            time.sleep(1)  # Rate limit between pairs

    def _analyze_and_trade(self, symbol: str) -> bool:
        """Analyze a pair and open trade if signal strong enough."""
        # Get multi-timeframe candles
        candles = self.market.get_multi_timeframe(symbol)
        if len(candles) < 2:
            return False

        # Multi-timeframe TA
        ta_result = self.ta.multi_timeframe_analysis(candles)
        consensus = ta_result.get("consensus", "SKIP")
        score = ta_result.get("consensus_score", 50)
        agreement = ta_result.get("tf_agreement", 0)

        # Fallback: if consensus is SKIP, check individual TFs for strong signals
        if consensus == "SKIP":
            tf_data = ta_result.get("timeframes", {})
            best_signal = None
            best_score = 0
            # Check all TFs for strong signals, prefer higher TFs
            for tf in ["4h", "1h", "15m", "5m"]:
                if tf in tf_data:
                    s = tf_data[tf].get("score", 50)
                    sig = tf_data[tf].get("signal", "SKIP")
                    if sig != "SKIP" and (s >= 70 or s <= 30):
                        # Stronger signals from higher TFs get less discount
                        discount = {"4h": 0.90, "1h": 0.85, "15m": 0.80, "5m": 0.75}
                        adj_score = s * discount.get(tf, 0.80)
                        if adj_score > best_score:
                            best_signal = sig
                            best_score = adj_score
            if best_signal:
                consensus = best_signal
                score = best_score
                logger.info(f"  {symbol}: TF fallback → {consensus} score={score:.1f}")
            else:
                return False

        # Confidence from score
        confidence = min(0.95, score / 100) if consensus == "LONG" else min(0.95, (100 - score) / 100)

        if confidence < 0.60:
            return False

        # Consecutive loss cooldown
        if self.consecutive_losses >= 3:
            logger.info(f"  Cooldown: {self.consecutive_losses} consecutive losses")
            return False

        # Get current price
        price = self.market.get_current_price(symbol)
        if not price:
            logger.info(f"  {symbol}: No price available")
            return False

        # AI confirmation (optional)
        if self.use_ai and self.ai:
            market_ctx = self.market.get_market_context(symbol)
            news_text = self.news.get_all_news(symbol)
            ai_result = self.ai.analyze_trade(symbol, ta_result, market_ctx, news_text)
            if ai_result:
                ai_action = ai_result.get("action", "SKIP")
                if ai_action == "SKIP" or ai_action != consensus:
                    logger.info(f"  {symbol}: AI says {ai_action}, TA says {consensus} — skip")
                    return False
                # Use AI's confidence if higher
                ai_conf = ai_result.get("confidence", 0)
                if ai_conf > confidence:
                    confidence = ai_conf

        # Position sizing
        side = consensus
        tf_5m = ta_result.get("timeframes", {}).get("5m", {})
        atr_val = tf_5m.get("atr", price * 0.01)
        levels = self.ta.calculate_sl_tp(price, side, atr_val)
        sl_dist_pct = levels["sl_distance_pct"]

        # Conservative leverage
        leverage = self._calc_leverage(confidence, sl_dist_pct)
        pos = self.risk.calculate_position(self.db.balance, price, sl_dist_pct, leverage, confidence)
        margin = pos["margin_required"]

        logger.info(f"  {symbol}: price=${price:,.2f} sl_pct={sl_dist_pct:.2f}% lev={leverage}x margin=${margin:.2f} bal={self.db.balance:.2f}")

        if margin > self.db.balance * 0.4 or margin < 1:
            logger.info(f"  {symbol}: Margin check failed (margin=${margin:.2f}, max=${self.db.balance * 0.4:.2f})")
            return False

        # Open trade
        signal = {
            "symbol": symbol, "side": side, "action": side,
            "entry_price": price, "quantity": pos["quantity"],
            "leverage": leverage, "margin": margin,
            "position_value": pos["position_value"],
            "stop_loss": levels["stop_loss"],
            "tp1": levels["tp1"], "tp2": levels["tp2"], "tp3": levels["tp3"],
            "sl_pct": sl_dist_pct, "confidence": confidence,
            "reasoning": f"TA score {score:.1f}, agreement {agreement:.0%}",
            "model": "TA" + ("+AI" if self.use_ai else ""),
            "ta_score": score,
        }

        result = self.db.open_trade(signal, cycle=self.cycle)
        trade_id = result["id"]

        icon = "LONG" if side == "LONG" else "SHORT"
        logger.info(
            f"  OPENED #{trade_id}: {icon} {symbol} @ ${price:,.2f} "
            f"| {leverage}x | margin ${margin:.2f} | conf {confidence:.0%}"
        )

        # Telegram alert
        tg_send(
            f"{'LONG' if side == 'LONG' else 'SHORT'} <b>{symbol}</b>\n"
            f"Entry: ${price:,.2f} | {leverage}x\n"
            f"SL: ${levels['stop_loss']:,.2f} | TP: ${levels['tp1']:,.2f}\n"
            f"Conf: {confidence:.0%} | #{trade_id}"
        )

        return True

    def _monitor_positions(self):
        """Check SL/TP for all open positions."""
        open_trades = self.db.get_open_trades()
        if not open_trades:
            return

        for trade in open_trades:
            symbol = trade["symbol"]
            price = self.market.get_current_price(symbol)
            if not price:
                continue

            side = trade["side"]
            entry = trade["entry_price"]
            sl = trade["stop_loss"]
            tp1 = trade["tp1"]
            trade_id = trade["id"]

            # Unrealized P&L
            if side == "LONG":
                pnl_pct = (price - entry) / entry * 100
            else:
                pnl_pct = (entry - price) / entry * 100

            # Check SL
            hit_sl = (side == "LONG" and price <= sl) or (side == "SHORT" and price >= sl)
            if hit_sl:
                result = self.db.close_trade(trade_id, price, "STOP_LOSS", self.cycle)
                self.consecutive_losses += 1
                logger.info(
                    f"  SL HIT #{trade_id} {symbol}: ${result.get('profit', 0):.2f} "
                    f"({result.get('profit_pct', 0):+.1f}%)"
                )
                tg_send(
                    f"SL #{trade_id} {symbol}\n"
                    f"P&L: ${result.get('profit', 0):.2f} ({result.get('profit_pct', 0):+.1f}%)\n"
                    f"Balance: ${self.db.balance:.2f}"
                )
                continue

            # Check TP1
            hit_tp = (side == "LONG" and price >= tp1) or (side == "SHORT" and price <= tp1)
            if hit_tp:
                result = self.db.close_trade(trade_id, price, "TP1", self.cycle)
                self.consecutive_losses = 0
                logger.info(
                    f"  TP1 HIT #{trade_id} {symbol}: +${result.get('profit', 0):.2f} "
                    f"({result.get('profit_pct', 0):+.1f}%)"
                )
                tg_send(
                    f"TP1 #{trade_id} {symbol}\n"
                    f"P&L: +${result.get('profit', 0):.2f} ({result.get('profit_pct', 0):+.1f}%)\n"
                    f"Balance: ${self.db.balance:.2f}"
                )

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
        return min(lev, int(os.getenv("MAX_LEVERAGE", "10")))

    def _sleep_monitor(self, duration: int):
        """Sleep while monitoring SL/TP every 15 seconds."""
        elapsed = 0
        while elapsed < duration:
            wait = min(15, duration - elapsed)
            time.sleep(wait)
            elapsed += wait

            # Quick SL check during sleep
            open_trades = self.db.get_open_trades()
            for trade in open_trades:
                p = self.market.get_current_price(trade["symbol"])
                if not p:
                    continue
                sl = trade["stop_loss"]
                side = trade["side"]
                if (side == "LONG" and p <= sl) or (side == "SHORT" and p >= sl):
                    result = self.db.close_trade(trade["id"], p, "SL_SLEEP", self.cycle)
                    self.consecutive_losses += 1
                    logger.warning(f"  EMERGENCY SL #{trade['id']} {trade['symbol']}")
                    tg_send(
                        f"EMERGENCY SL #{trade['id']} {trade['symbol']}\n"
                        f"P&L: ${result.get('profit', 0):.2f}"
                    )

    def _check_daily_summary(self):
        """Send daily Telegram summary once per day."""
        today = datetime.now().strftime("%Y-%m-%d")
        if self.state.get("last_daily_summary") == today:
            return

        stats = self.db.get_stats()
        self.state["last_daily_summary"] = today
        save_state(self.state)

        tg_send(
            f"<b>Daily Summary — Day {int(self.elapsed_days) + 1}/{DEMO_DURATION_DAYS}</b>\n\n"
            f"Balance: ${stats['balance']:.2f}\n"
            f"P&L: ${stats['total_pnl']:.2f} ({stats['roi']:.1f}%)\n"
            f"Today: ${stats['daily_pnl']:.2f}\n"
            f"Trades: {stats['total_trades']} (WR: {stats['win_rate']:.1f}%)\n"
            f"Wins: {stats['wins']} | Losses: {stats['losses']}\n"
            f"Open: {stats['open_positions']}\n"
            f"Remaining: {self.remaining}"
        )

    def _render_dashboard(self):
        """Print terminal dashboard."""
        stats = self.db.get_stats()
        open_trades = self.db.get_open_trades()
        pnl_color = C.G if stats["total_pnl"] >= 0 else C.R

        print(f"\033[2J\033[H", end="")
        print(f"""
{C.CY}{'='*60}
  DEMO TRADING — Day {self.elapsed_days:.1f}/{DEMO_DURATION_DAYS} | Remaining: {self.remaining}
{'='*60}{C.RST}
  Cycle: #{self.cycle} | Pairs: {len(TRADING_PAIRS)} | AI: {'ON' if self.use_ai else 'OFF'}
  Scan: every {SCAN_INTERVAL}s | Started: {self.start_time.strftime('%Y-%m-%d %H:%M')}

  Balance: ${stats['balance']:.2f}  |  Starting: ${stats['starting_balance']:.2f}
  P&L: {pnl_color}${stats['total_pnl']:.2f}{C.RST}  |  Daily: {pnl_color}${stats['daily_pnl']:.2f}{C.RST}
  ROI: {pnl_color}{stats['roi']:.1f}%{C.RST}  |  Win Rate: {C.G if stats['win_rate'] >= 50 else C.R}{stats['win_rate']:.1f}%{C.RST}
  Wins: {stats['wins']}  |  Losses: {stats['losses']}  |  Open: {stats['open_positions']}
  Fees: ${stats['total_fees']:.4f}  |  Consec. Losses: {self.consecutive_losses}
{C.CY}{'─'*60}{C.RST}""")

        if open_trades:
            print(f"  {C.B}Open Positions:{C.RST}")
            for t in open_trades:
                p = self.market.get_current_price(t["symbol"])
                if p:
                    if t["side"] == "LONG":
                        upnl = (p - t["entry_price"]) / t["entry_price"] * 100
                    else:
                        upnl = (t["entry_price"] - p) / t["entry_price"] * 100
                    col = C.G if upnl >= 0 else C.R
                    print(f"    {t['symbol']:<10} {t['side']:<5} {t['leverage']}x "
                          f"| Entry ${t['entry_price']:,.2f} -> ${p:,.2f} "
                          f"| {col}{upnl:+.2f}%{C.RST}")
        print(f"{C.CY}{'─'*60}{C.RST}")

    def _final_report(self):
        """Print and send final 7-day report."""
        stats = self.db.get_stats()
        closed = self.db.get_closed_trades(limit=100)

        report = f"""
{C.CY}{'='*60}
  7-DAY DEMO TRADING — FINAL REPORT
{'='*60}{C.RST}

  Starting Balance: ${stats['starting_balance']:.2f}
  Final Balance:    ${stats['balance']:.2f}
  Net P&L:          {C.G if stats['total_pnl'] >= 0 else C.R}${stats['total_pnl']:.2f}{C.RST}
  ROI:              {C.G if stats['roi'] >= 0 else C.R}{stats['roi']:.1f}%{C.RST}

  Total Trades: {stats['total_trades']}
  Wins:         {stats['wins']}
  Losses:       {stats['losses']}
  Win Rate:     {stats['win_rate']:.1f}%
  Total Fees:   ${stats['total_fees']:.4f}

{C.CY}{'='*60}{C.RST}
"""
        print(report)

        # Telegram final report
        tg_send(
            f"<b>7-DAY DEMO COMPLETE</b>\n\n"
            f"Balance: ${stats['balance']:.2f}\n"
            f"P&L: ${stats['total_pnl']:.2f} ({stats['roi']:.1f}%)\n"
            f"Trades: {stats['total_trades']}\n"
            f"Win Rate: {stats['win_rate']:.1f}%\n"
            f"Wins: {stats['wins']} | Losses: {stats['losses']}"
        )

    def _print_banner(self):
        print(f"""
{C.CY}
  ╔═══════════════════════════════════════════╗
  ║   CRYPTO FUTURES — 7 DAY DEMO TRADING    ║
  ║                                           ║
  ║   Paper trading with live market data     ║
  ║   No real money — demo account only       ║
  ╚═══════════════════════════════════════════╝
{C.RST}""")
        logger.info(f"Pairs: {', '.join(TRADING_PAIRS)}")
        logger.info(f"Balance: ${self.db.balance:.2f}")
        logger.info(f"Duration: {DEMO_DURATION_DAYS} days")
        logger.info(f"AI: {'ON' if self.use_ai else 'OFF'}")
        if self.cycle > 0:
            logger.info(f"RESUMING from cycle #{self.cycle} (day {self.elapsed_days:.1f})")


# ─── Status command ────────────────────────────────────
def print_status():
    state = load_state()
    if not state:
        print("  No demo running. Start with: python run_demo.py")
        return

    db = TradeDB(DB_PATH, STARTING_BALANCE)
    stats = db.get_stats()
    start = datetime.fromisoformat(state["start_time"])
    elapsed = (datetime.now() - start).total_seconds() / 86400

    print(f"""
{C.CY}  Demo Status{C.RST}
  {'─'*40}
  Started: {start.strftime('%Y-%m-%d %H:%M')}
  Day: {elapsed:.1f} / {DEMO_DURATION_DAYS}
  Cycles: {state.get('cycle', 0)}

  Balance: ${stats['balance']:.2f}
  P&L: ${stats['total_pnl']:.2f} ({stats['roi']:.1f}%)
  Trades: {stats['total_trades']}
  Win Rate: {stats['win_rate']:.1f}%
  Wins: {stats['wins']} | Losses: {stats['losses']}
  Open: {stats['open_positions']}
""")


# ─── Entry Point ───────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="7-Day Demo Trading")
    parser.add_argument("--reset", action="store_true", help="Reset and start fresh")
    parser.add_argument("--status", action="store_true", help="Show current status")
    parser.add_argument("--no-ai", action="store_true", help="Disable AI (TA-only)")
    args = parser.parse_args()

    if args.status:
        print_status()
        return

    if args.reset:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        print(f"  {C.G}Demo reset.{C.RST}")

    use_ai = not args.no_ai
    runner = DemoRunner(use_ai=use_ai)
    runner.run()


if __name__ == "__main__":
    main()
