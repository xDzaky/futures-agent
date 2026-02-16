"""
Crypto Futures AI Trading Agent — Main Loop
=============================================
Autonomous AI agent for crypto futures trading:

→ Scans configured pairs every 30 seconds
→ Multi-timeframe TA (1m, 5m, 15m, 1h, 4h)
→ AI analysis via Groq (Llama 3.3 70B FREE)
→ Risk-based position sizing (max 2% per trade)
→ Automatic SL/TP monitoring
→ News-reactive trading (breaking news → instant analysis)
→ Full SQLite trade tracking & P&L
→ Telegram alerts & bot commands

TESTNET MODE: Paper trading on Binance Futures Testnet.
No real money used until switched to live.
"""

import os
import sys
import time
import logging
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv

from exchange import FuturesExchange
from market_data import MarketData
from technical import TechnicalAnalyzer
from ai_analyzer import AIAnalyzer
from risk_manager import RiskManager
from trade_db import TradeDB
from news_feeds import NewsFeedManager

load_dotenv()

# ─── Config ────────────────────────────────────────────
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL_SECONDS", "30"))
TRADING_PAIRS = os.getenv(
    "TRADING_PAIRS", "BTC/USDT,ETH/USDT,SOL/USDT"
).split(",")
STARTING_BALANCE = float(os.getenv("STARTING_BALANCE", "1000.0"))
USE_TESTNET = os.getenv("USE_TESTNET", "true").lower() == "true"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


# ─── Colors ────────────────────────────────────────────
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    WHITE = "\033[97m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


# ─── Logging Setup ─────────────────────────────────────
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s │ %(name)-12s │ %(levelname)-5s │ %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy loggers
    logging.getLogger("ccxt").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    return logging.getLogger("agent")


logger = setup_logging()


# ─── Telegram Notifier ─────────────────────────────────
class TelegramNotifier:
    """Send trade alerts to Telegram."""

    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.enabled = bool(self.token and self.chat_id)

    def send(self, message: str):
        if not self.enabled:
            return
        try:
            import requests
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            requests.post(url, json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
            }, timeout=10)
        except Exception as e:
            logger.debug(f"Telegram send error: {e}")

    def trade_opened(self, signal: dict, result: dict):
        symbol = signal.get("symbol", "?")
        side = signal.get("side", "?")
        entry = signal.get("entry_price", 0)
        leverage = signal.get("leverage", 1)
        margin = result.get("margin", 0)
        conf = signal.get("confidence", 0)
        sl = signal.get("stop_loss", 0)
        tp1 = signal.get("tp1", 0)

        msg = (
            f"🔔 <b>NEW TRADE</b>\n\n"
            f"{'🟢 LONG' if side == 'LONG' else '🔴 SHORT'} {symbol}\n"
            f"Entry: ${entry:,.2f}\n"
            f"Leverage: {leverage}x\n"
            f"Margin: ${margin:.2f}\n"
            f"Confidence: {conf:.0%}\n"
            f"SL: ${sl:,.2f}\n"
            f"TP1: ${tp1:,.2f}\n"
            f"#{signal.get('trade_id', 0)}"
        )
        self.send(msg)

    def trade_closed(self, result: dict):
        symbol = result.get("symbol", "?")
        side = result.get("side", "?")
        profit = result.get("profit", 0)
        pnl_pct = result.get("profit_pct", 0)
        reason = result.get("reason", "?")
        balance = result.get("balance", 0)

        icon = "✅" if profit > 0 else "❌"
        msg = (
            f"{icon} <b>TRADE CLOSED</b>\n\n"
            f"{'🟢' if side == 'LONG' else '🔴'} {symbol} ({side})\n"
            f"P&L: {'🟢' if profit > 0 else '🔴'} ${profit:.2f} ({pnl_pct:+.1f}%)\n"
            f"Reason: {reason}\n"
            f"Balance: ${balance:.2f}"
        )
        self.send(msg)

    def breaking_news(self, title: str, impact: str):
        msg = (
            f"📰 <b>BREAKING NEWS</b>\n\n"
            f"{title}\n"
            f"Impact: {impact}"
        )
        self.send(msg)


# ─── Telegram Bot (command handler) ───────────────────
class TelegramBot:
    """Handles Telegram bot commands via long-polling."""

    def __init__(self, db: TradeDB, notifier: TelegramNotifier):
        self.db = db
        self.notifier = notifier
        self.token = TELEGRAM_BOT_TOKEN
        self.offset = 0
        self.running = False

    def start(self):
        if not self.token:
            return
        self.running = True
        thread = threading.Thread(target=self._poll_loop, daemon=True)
        thread.start()
        logger.info("Telegram bot started (background thread)")

    def _poll_loop(self):
        import requests
        while self.running:
            try:
                url = f"https://api.telegram.org/bot{self.token}/getUpdates"
                resp = requests.get(url, params={
                    "offset": self.offset, "timeout": 30
                }, timeout=35)
                if resp.status_code == 200:
                    updates = resp.json().get("result", [])
                    for update in updates:
                        self.offset = update["update_id"] + 1
                        self._handle_update(update)
            except Exception:
                time.sleep(5)

    def _handle_update(self, update: dict):
        msg = update.get("message", {})
        text = msg.get("text", "").strip()
        chat_id = msg.get("chat", {}).get("id")

        if not text or not chat_id:
            return

        if text.startswith("/"):
            cmd = text.split()[0].lower()
            self._handle_command(cmd, chat_id)

    def _handle_command(self, cmd: str, chat_id):
        import requests

        handlers = {
            "/start": self._cmd_start,
            "/help": self._cmd_help,
            "/balance": self._cmd_balance,
            "/positions": self._cmd_positions,
            "/stats": self._cmd_stats,
            "/trades": self._cmd_trades,
        }

        handler = handlers.get(cmd, self._cmd_unknown)
        reply = handler()

        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            requests.post(url, json={
                "chat_id": chat_id,
                "text": reply,
                "parse_mode": "HTML",
            }, timeout=10)
        except Exception:
            pass

    def _cmd_start(self) -> str:
        return (
            "🤖 <b>Futures Trading Agent</b>\n\n"
            "Active and monitoring markets 24/7.\n"
            "Use /help to see available commands."
        )

    def _cmd_help(self) -> str:
        return (
            "📋 <b>Commands</b>\n\n"
            "/balance — Current balance & P&L\n"
            "/positions — Open positions\n"
            "/stats — Trading statistics\n"
            "/trades — Recent closed trades\n"
        )

    def _cmd_balance(self) -> str:
        stats = self.db.get_stats()
        return (
            f"💰 <b>Balance</b>\n\n"
            f"Balance: ${stats['balance']:.2f}\n"
            f"Total P&L: ${stats['total_pnl']:.2f}\n"
            f"Daily P&L: ${stats['daily_pnl']:.2f}\n"
            f"ROI: {stats['roi']:.1f}%\n"
            f"Starting: ${stats['starting_balance']:.2f}"
        )

    def _cmd_positions(self) -> str:
        positions = self.db.get_open_trades()
        if not positions:
            return "📭 No open positions."

        lines = ["📊 <b>Open Positions</b>\n"]
        for p in positions:
            icon = "🟢" if p["side"] == "LONG" else "🔴"
            lines.append(
                f"{icon} {p['symbol']} {p['side']} {p['leverage']}x\n"
                f"   Entry: ${p['entry_price']:,.2f} | "
                f"Margin: ${p['margin']:.2f}"
            )
        return "\n".join(lines)

    def _cmd_stats(self) -> str:
        stats = self.db.get_stats()
        return (
            f"📈 <b>Trading Stats</b>\n\n"
            f"Total Trades: {stats['total_trades']}\n"
            f"Wins: {stats['wins']} | Losses: {stats['losses']}\n"
            f"Win Rate: {stats['win_rate']:.1f}%\n"
            f"ROI: {stats['roi']:.1f}%\n"
            f"Total Fees: ${stats['total_fees']:.4f}\n"
            f"Open: {stats['open_positions']}"
        )

    def _cmd_trades(self) -> str:
        trades = self.db.get_closed_trades(limit=5)
        if not trades:
            return "📭 No closed trades yet."

        lines = ["📋 <b>Recent Trades</b>\n"]
        for t in trades:
            icon = "✅" if t["profit"] > 0 else "❌"
            lines.append(
                f"{icon} {t['symbol']} {t['side']}\n"
                f"   P&L: ${t['profit']:.2f} ({t['profit_pct']:+.1f}%) | "
                f"{t['close_reason']}"
            )
        return "\n".join(lines)

    def _cmd_unknown(self) -> str:
        return "Unknown command. Use /help for available commands."


# ─── Dashboard ─────────────────────────────────────────
class Dashboard:
    """Terminal dashboard display."""

    def __init__(self, db: TradeDB, start_time: datetime):
        self.db = db
        self.start_time = start_time

    def render(self, cycle: int, status: str = "SCANNING"):
        stats = self.db.get_stats()
        uptime = self._uptime()
        open_trades = self.db.get_open_trades()

        mode = f"{Colors.YELLOW}TESTNET{Colors.RESET}" if USE_TESTNET else f"{Colors.RED}LIVE{Colors.RESET}"
        alive = stats["balance"] > 10
        status_color = Colors.GREEN if alive else Colors.RED
        pnl_color = Colors.GREEN if stats["total_pnl"] >= 0 else Colors.RED

        # Clear screen
        print("\033[2J\033[H", end="")

        print(f"""
{Colors.CYAN}╔══════════════════════════════════════════════════════════════╗
║  🤖 CRYPTO FUTURES AI TRADING AGENT                         ║
╠══════════════════════════════════════════════════════════════╣{Colors.RESET}
  Mode: {mode}  │  Status: {status_color}{status}{Colors.RESET}  │  Uptime: {uptime}
  Cycle: #{cycle}  │  Pairs: {len(TRADING_PAIRS)}  │  Interval: {SCAN_INTERVAL}s

{Colors.CYAN}╠══════════════════════════════════════════════════════════════╣{Colors.RESET}
  💰 Balance: ${stats['balance']:.2f}  │  Starting: ${stats['starting_balance']:.2f}
  📊 P&L: {pnl_color}${stats['total_pnl']:.2f}{Colors.RESET}  │  Daily: {pnl_color}${stats['daily_pnl']:.2f}{Colors.RESET}
  📈 ROI: {pnl_color}{stats['roi']:.1f}%{Colors.RESET}  │  Win Rate: {stats['win_rate']:.1f}%
  🏆 Wins: {stats['wins']}  │  Losses: {stats['losses']}  │  Open: {stats['open_positions']}
  💸 Total Fees: ${stats['total_fees']:.4f}
{Colors.CYAN}╠══════════════════════════════════════════════════════════════╣{Colors.RESET}""")

        # Open positions
        if open_trades:
            print(f"  {Colors.BOLD}Open Positions:{Colors.RESET}")
            for t in open_trades[:5]:
                icon = "🟢" if t["side"] == "LONG" else "🔴"
                print(
                    f"   {icon} {t['symbol']} {t['side']} {t['leverage']}x "
                    f"│ Entry: ${t['entry_price']:,.2f} "
                    f"│ Margin: ${t['margin']:.2f} "
                    f"│ SL: ${t['stop_loss']:,.2f}"
                )
        else:
            print(f"  {Colors.DIM}No open positions{Colors.RESET}")

        print(f"""{Colors.CYAN}╠══════════════════════════════════════════════════════════════╣{Colors.RESET}
  {Colors.BOLD}Activity Log:{Colors.RESET}""")

    def _uptime(self) -> str:
        delta = datetime.now() - self.start_time
        total = int(delta.total_seconds())
        h, m, s = total // 3600, (total % 3600) // 60, total % 60
        return f"{h:02d}:{m:02d}:{s:02d}"


# ─── Main Agent Class ──────────────────────────────────
class FuturesAgent:
    """Main futures trading agent — orchestrates all modules."""

    def __init__(self):
        self.cycle = 0
        self.start_time = datetime.now()

        # Initialize modules
        logger.info("Initializing modules...")
        self.exchange = FuturesExchange()
        self.market_data = MarketData(self.exchange)
        self.technical = TechnicalAnalyzer()
        self.ai = AIAnalyzer()
        self.risk = RiskManager()
        self.db = TradeDB(starting_balance=STARTING_BALANCE)
        self.news = NewsFeedManager()
        self.notifier = TelegramNotifier()
        self.dashboard = Dashboard(self.db, self.start_time)
        self.bot = TelegramBot(self.db, self.notifier)

        logger.info("All modules initialized")

    def run(self):
        """Main agent loop."""
        print(f"\n{Colors.CYAN}{'='*60}")
        print("  CRYPTO FUTURES AI TRADING AGENT")
        print(f"  Mode: {'TESTNET' if USE_TESTNET else 'LIVE'}")
        print(f"  Pairs: {', '.join(TRADING_PAIRS)}")
        print(f"  Balance: ${self.db.balance:.2f}")
        print(f"  Scan Interval: {SCAN_INTERVAL}s")
        print(f"{'='*60}{Colors.RESET}\n")

        # Start Telegram bot
        self.bot.start()

        # Notify startup
        self.notifier.send(
            f"🚀 <b>Agent Started</b>\n"
            f"Mode: {'TESTNET' if USE_TESTNET else 'LIVE'}\n"
            f"Pairs: {len(TRADING_PAIRS)}\n"
            f"Balance: ${self.db.balance:.2f}"
        )

        while True:
            try:
                self.cycle += 1
                self._run_cycle()

                # Sleep with countdown and news monitoring
                self._sleep_with_monitoring(SCAN_INTERVAL)

            except KeyboardInterrupt:
                logger.info("Agent stopped by user")
                self.notifier.send("⏹ Agent stopped by user")
                break
            except Exception as e:
                logger.error(f"Cycle error: {e}")
                time.sleep(10)

    def _run_cycle(self):
        """Execute one full scan → analyze → trade cycle."""
        self.dashboard.render(self.cycle, "SCANNING")
        log = self._log

        log(f"{'─'*50}")
        log(f"📡 Cycle #{self.cycle} — Scanning {len(TRADING_PAIRS)} pairs...")

        # ── Step 1: Pre-trade safety check ──
        stats = self.db.get_stats()
        open_count = stats["open_positions"]
        check = self.risk.check_can_trade(
            self.db.balance, open_count, self.db.daily_pnl
        )

        if not check["can_trade"]:
            log(f"⛔ Cannot trade: {check['reason']}")
            # Still monitor open positions
            self._monitor_open_positions()
            return

        # ── Step 2: Check and monitor open positions ──
        self._monitor_open_positions()

        # ── Step 3: Scan each pair ──
        for symbol in TRADING_PAIRS:
            symbol = symbol.strip()
            if not symbol:
                continue

            # Skip if already have open position for this pair
            if self.db.is_symbol_open(symbol):
                log(f"  ⏭ {symbol} — already open, skipping")
                continue

            try:
                self._analyze_pair(symbol)
            except Exception as e:
                log(f"  ❌ {symbol} error: {e}")

            time.sleep(0.5)  # Rate limit between pairs

        # ── Step 4: Check breaking news ──
        self._check_breaking_news()

        log(f"✅ Cycle #{self.cycle} complete | "
            f"Balance: ${self.db.balance:.2f} | "
            f"AI calls: {self.ai.total_calls}")

    def _analyze_pair(self, symbol: str):
        """Analyze a single trading pair."""
        log = self._log

        log(f"\n  📊 Analyzing {symbol}...")

        # ── Get multi-timeframe candles ──
        candles = self.market_data.get_multi_timeframe(symbol)
        if not candles:
            log(f"  ⚠ {symbol}: No candle data")
            return

        # ── Technical Analysis ──
        ta_result = self.technical.multi_timeframe_analysis(candles)
        consensus = ta_result.get("consensus", "SKIP")
        ta_score = ta_result.get("consensus_score", 50)

        log(f"  📈 TA: {consensus} (score: {ta_score})")

        # Skip if no clear signal
        if consensus == "SKIP":
            log(f"  ⏭ {symbol}: No clear signal, skipping")
            return

        # ── Market Context ──
        market_ctx = self.market_data.get_market_context(symbol)
        price = market_ctx.get("price", 0)
        if not price:
            log(f"  ⚠ {symbol}: Cannot get price")
            return

        # ── News for this pair ──
        coin = symbol.split("/")[0]
        news_text = self.news.get_all_news(symbol)

        # ── AI Analysis ──
        log(f"  🧠 AI analyzing {symbol}...")
        ai_result = self.ai.analyze_trade(symbol, ta_result, market_ctx, news_text)

        if not ai_result:
            log(f"  ⚠ {symbol}: AI returned no result")
            return

        action = ai_result.get("action", "SKIP")
        confidence = ai_result.get("confidence", 0)
        reasoning = ai_result.get("reasoning", "")

        log(f"  🤖 AI: {action} (conf: {confidence:.0%})")
        log(f"     Reason: {reasoning[:80]}")

        # Skip if AI says skip or low confidence
        if action == "SKIP" or confidence < 0.65:
            log(f"  ⏭ {symbol}: AI says {action} (conf: {confidence:.0%})")
            return

        # ── Position Sizing ──
        side = action  # LONG or SHORT
        sl_pct = ai_result.get("sl_pct", 1.5)
        leverage = ai_result.get("leverage", 3)

        position = self.risk.calculate_position(
            balance=self.db.balance,
            price=price,
            sl_pct=sl_pct,
            leverage=leverage,
            confidence=confidence,
        )

        margin = position["margin_required"]
        qty = position["quantity"]
        pos_value = position["position_value"]
        actual_leverage = position["leverage"]

        log(f"  💼 Position: ${pos_value:.2f} ({actual_leverage}x) "
            f"| Margin: ${margin:.2f} | Risk: ${position['risk_amount']:.2f}")

        # ── Calculate SL/TP prices ──
        tf_5m = ta_result.get("timeframes", {}).get("5m", {})
        atr = tf_5m.get("atr", price * 0.01)  # Fallback 1% if no ATR

        levels = self.technical.calculate_sl_tp(price, side, atr)
        stop_loss = levels["stop_loss"]
        tp1 = levels["tp1"]
        tp2 = levels["tp2"]
        tp3 = levels["tp3"]

        # Use AI-suggested SL if tighter
        if side == "LONG":
            ai_sl = price * (1 - sl_pct / 100)
            stop_loss = max(stop_loss, ai_sl)
        else:
            ai_sl = price * (1 + sl_pct / 100)
            stop_loss = min(stop_loss, ai_sl)

        # ── Execute Trade (paper trade via DB) ──
        signal = {
            "symbol": symbol,
            "side": side,
            "action": action,
            "entry_price": price,
            "quantity": qty,
            "leverage": actual_leverage,
            "margin": margin,
            "position_value": pos_value,
            "stop_loss": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "sl_pct": sl_pct,
            "confidence": confidence,
            "reasoning": reasoning,
            "model": ai_result.get("model", ""),
            "ta_score": ta_score,
        }

        result = self.db.open_trade(signal, cycle=self.cycle)
        trade_id = result["id"]

        color = Colors.GREEN if side == "LONG" else Colors.RED
        log(f"\n  {color}{'🟢' if side == 'LONG' else '🔴'} "
            f"OPENED #{trade_id}: {side} {symbol} @ ${price:,.2f}{Colors.RESET}")
        log(f"     Leverage: {actual_leverage}x | Margin: ${margin:.2f}")
        log(f"     SL: ${stop_loss:,.2f} | TP1: ${tp1:,.2f} | TP2: ${tp2:,.2f}")

        # Telegram alert
        signal["trade_id"] = trade_id
        self.notifier.trade_opened(signal, result)

    def _monitor_open_positions(self):
        """Check SL/TP levels for all open positions."""
        log = self._log
        open_trades = self.db.get_open_trades()

        if not open_trades:
            return

        log(f"\n  👁 Monitoring {len(open_trades)} open position(s)...")

        for trade in open_trades:
            symbol = trade["symbol"]
            trade_id = trade["id"]
            side = trade["side"]
            entry = trade["entry_price"]
            sl = trade["stop_loss"]
            tp1 = trade["tp1"]
            tp2 = trade["tp2"]
            tp3 = trade["tp3"]
            leverage = trade["leverage"]

            # Get current price
            current_price = self.market_data.get_current_price(symbol)
            if not current_price:
                continue

            # Calculate unrealized P&L
            if side == "LONG":
                pnl_pct = (current_price - entry) / entry * 100
            else:
                pnl_pct = (entry - current_price) / entry * 100

            pnl_color = Colors.GREEN if pnl_pct >= 0 else Colors.RED
            log(f"    #{trade_id} {symbol} {side}: "
                f"Entry ${entry:,.2f} → Now ${current_price:,.2f} "
                f"| {pnl_color}{pnl_pct:+.2f}%{Colors.RESET}")

            # ── Check Stop Loss ──
            hit_sl = False
            if side == "LONG" and current_price <= sl:
                hit_sl = True
            elif side == "SHORT" and current_price >= sl:
                hit_sl = True

            if hit_sl:
                log(f"    🛑 SL HIT #{trade_id} {symbol}")
                result = self.db.close_trade(
                    trade_id, current_price, "STOP_LOSS", self.cycle
                )
                log(f"    ❌ Closed: ${result.get('profit', 0):.2f} "
                    f"({result.get('profit_pct', 0):+.1f}%)")
                self.notifier.trade_closed(result)
                continue

            # ── Check Take Profits ──
            if tp1 and self._tp_hit(side, current_price, tp1):
                log(f"    💰 TP1 HIT #{trade_id} {symbol}")
                result = self.db.close_trade(
                    trade_id, current_price, "TP1", self.cycle
                )
                log(f"    ✅ Closed at TP1: ${result.get('profit', 0):.2f} "
                    f"({result.get('profit_pct', 0):+.1f}%)")
                self.notifier.trade_closed(result)
                continue

            # ── Trailing Stop Check ──
            sl_pct = trade.get("sl_pct", 1.5)
            trail = self.risk.should_close_early(
                entry, current_price, side, sl_pct, pnl_pct
            )
            if trail["action"] == "TRAIL_STOP":
                log(f"    📐 Trailing stop for #{trade_id}: {trail['reason']}")

    def _tp_hit(self, side: str, current: float, target: float) -> bool:
        if side == "LONG":
            return current >= target
        return current <= target

    def _check_breaking_news(self):
        """Check for high-impact news and react."""
        log = self._log
        breaking = self.news.check_breaking_news()

        if not breaking:
            return

        for article in breaking[:2]:
            title = article["title"]
            keyword = article.get("matched_keyword", "")
            log(f"\n  📰 Breaking: {title[:70]}...")

            # AI analysis of news impact
            impact = self.ai.analyze_news_impact(title, "BTC")
            if impact:
                severity = impact.get("severity", 0)
                direction = impact.get("impact", "NEUTRAL")
                log(f"     Impact: {direction} (severity: {severity}/10)")

                # High-severity news: alert via Telegram
                if severity >= 7:
                    self.notifier.breaking_news(
                        title[:100],
                        f"{direction} (severity: {severity}/10)"
                    )

    def _sleep_with_monitoring(self, duration: int):
        """Sleep between cycles while monitoring positions and news."""
        log = self._log
        elapsed = 0
        check_interval = 10  # Check positions every 10s during sleep

        while elapsed < duration:
            wait = min(check_interval, duration - elapsed)
            time.sleep(wait)
            elapsed += wait

            # Quick position check during sleep
            if elapsed % 10 == 0:
                open_trades = self.db.get_open_trades()
                for trade in open_trades:
                    symbol = trade["symbol"]
                    current = self.market_data.get_current_price(symbol)
                    if not current:
                        continue

                    side = trade["side"]
                    sl = trade["stop_loss"]

                    # Emergency SL check during sleep
                    if side == "LONG" and current <= sl:
                        log(f"  🚨 EMERGENCY SL: #{trade['id']} {symbol}")
                        result = self.db.close_trade(
                            trade["id"], current, "SL_SLEEP", self.cycle
                        )
                        self.notifier.trade_closed(result)
                    elif side == "SHORT" and current >= sl:
                        log(f"  🚨 EMERGENCY SL: #{trade['id']} {symbol}")
                        result = self.db.close_trade(
                            trade["id"], current, "SL_SLEEP", self.cycle
                        )
                        self.notifier.trade_closed(result)

        # Update dashboard
        self.dashboard.render(self.cycle, "WAITING")

    def _log(self, msg: str):
        """Print to terminal activity log."""
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"  {Colors.DIM}{ts}{Colors.RESET} │ {msg}")


# ─── Entry Point ────────────────────────────────────────
def main():
    print(f"""
{Colors.CYAN}
  ╔═══════════════════════════════════════════╗
  ║   🤖 CRYPTO FUTURES AI TRADING AGENT     ║
  ║                                           ║
  ║   TA + AI + Risk Management + News        ║
  ║   Powered by Groq Llama 3.3 70B (FREE)   ║
  ╚═══════════════════════════════════════════╝
{Colors.RESET}""")

    # Pre-flight checks
    if not os.getenv("GROQ_API_KEY"):
        print(f"{Colors.RED}❌ GROQ_API_KEY not set in .env{Colors.RESET}")
        sys.exit(1)

    if USE_TESTNET:
        print(f"  {Colors.YELLOW}⚠ TESTNET MODE — Paper trading only{Colors.RESET}")
        if not os.getenv("BINANCE_TESTNET_KEY"):
            print(f"  {Colors.YELLOW}⚠ No Binance testnet keys — using public API only{Colors.RESET}")
    else:
        print(f"  {Colors.RED}🔴 LIVE MODE — Real money!{Colors.RESET}")
        confirm = input("  Type 'YES' to confirm: ")
        if confirm != "YES":
            print("  Aborted.")
            sys.exit(0)

    print()

    agent = FuturesAgent()
    agent.run()


if __name__ == "__main__":
    main()
