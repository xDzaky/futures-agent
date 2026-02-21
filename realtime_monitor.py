"""
Real-Time Telegram Signal Monitor + Auto-Trader
==================================================
Event-driven system that monitors ALL Telegram channels in real-time.
When a new message is posted, it instantly:
1. Classifies: SIGNAL / NEWS / ANALYSIS / SKIP
2. Parses entry/TP/SL from structured signals
3. AI-analyzes unstructured text (Groq Llama, supports Indonesian)
4. AI-analyzes chart images (Gemini Vision)
5. Confirms with Technical Analysis
6. Executes trade with paper trading ($50 demo)

Architecture:
  Telethon events.NewMessage → classify → parse/analyze → TA confirm → execute

No polling. No OpenClaw. Pure Telethon event handlers.

Usage:
    python realtime_monitor.py [--reset] [--balance 50] [--no-ta]
    python realtime_monitor.py --status
    python realtime_monitor.py --list-channels
"""

import os
import sys
import json
import time
import signal as sig_module
import logging
import asyncio
import argparse
import re
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

# ─── Logging ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
_fh = logging.FileHandler("realtime_debug.log", mode="a")
_fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-5s | %(message)s", datefmt="%H:%M:%S"))
logging.getLogger().addHandler(_fh)
logging.getLogger("ccxt").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("telethon").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("realtime")


# ─── Telegram bot helper ──────────────────────────────
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def tg_send(msg: str):
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=5)
    except Exception:
        pass


def tg_get_updates(offset: int = 0, timeout: int = 30) -> List[Dict]:
    """Get updates from Telegram Bot API (long polling)."""
    if not BOT_TOKEN:
        return []
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
        params = {"offset": offset, "timeout": timeout}
        resp = requests.get(url, params=params, timeout=timeout + 5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("result", [])
    except Exception:
        pass
    return []


# ─── Channel Configuration ──────────────────────────────
# Categorized by quality and type based on our scan

SIGNAL_CHANNELS = {
    # ══════════════════════════════════════════════════════════
    # TIER 1: Structured signals (entry/TP/SL format) — parse directly
    # ══════════════════════════════════════════════════════════
    "@binance_360": {"tier": 1, "type": "signal", "name": "Binance 360"},
    1700533698: {"tier": 1, "type": "signal", "name": "Crypto Bulls"},
    1410449050: {"tier": 1, "type": "signal", "name": "Rose Paid Crypto Free"},
    1652601224: {"tier": 1, "type": "signal", "name": "Crypto World Updates"},
    "@binancekillers": {"tier": 1, "type": "signal", "name": "Binance Killers"},
    "@chiefhanfreesignal": {"tier": 1, "type": "signal", "name": "Chiefhan Official"},
    1358469005: {"tier": 1, "type": "signal", "name": "Snipe Trading Alex"},
    "@Whales_Pumps": {"tier": 1, "type": "signal", "name": "Whales Pumps"},
    "@BitcoinBrosAlerts": {"tier": 1, "type": "signal", "name": "Bitcoin Bros Alerts"},
    "@ksnsndhsjj": {"tier": 1, "type": "signal", "name": "Signal Crypto"},
    "@brianzahir": {"tier": 1, "type": "signal", "name": "Signal Coin Abal"},
    1895315984: {"tier": 1, "type": "signal", "name": "Crypto Spider Scalper"},
    2377213432: {"tier": 1, "type": "signal", "name": "Alpha Scalper"},
    "@Klausoneth": {"tier": 1, "type": "signal", "name": "Klaus on ETH"},
    1590450482: {"tier": 1, "type": "signal", "name": "The Crypto Trader"},
    3185887764: {"tier": 1, "type": "signal", "name": "The Crypto Ghosts"},
    "@acmirorwell": {"tier": 1, "type": "signal", "name": "Mirror Crypto Well"},
    1598691683: {"tier": 1, "type": "signal", "name": "Crypto Devil"},
    "@tpmafiatradingpro": {"tier": 1, "type": "signal", "name": "Mafia Trading Pro"},
    1391574614: {"tier": 1, "type": "signal", "name": "Bitcoin Bulls"},
    2150935838: {"tier": 1, "type": "signal", "name": "BitcoinBoss"},

    # ══════════════════════════════════════════════════════════
    # TIER 2: Analysis channels (AI interprets direction)
    # ══════════════════════════════════════════════════════════
    "@MWcryptojournal": {"tier": 2, "type": "analysis", "name": "Wyann's Journal"},
    "@RosePremiumm": {"tier": 2, "type": "analysis", "name": "Rose Premium"},
    "@kjoacademy": {"tier": 2, "type": "analysis", "name": "KJo Academy"},
    "@evolution_trading": {"tier": 2, "type": "analysis", "name": "Evolution Trading"},
    "@cryptoteknikal_id": {"tier": 2, "type": "analysis", "name": "Crypto Teknikal"},
    "@kjocryptochannel": {"tier": 2, "type": "analysis", "name": "KJo Backup"},
    "@Dinotimecycle": {"tier": 2, "type": "analysis", "name": "Dino Smart Money"},
    "@cryptocium": {"tier": 2, "type": "analysis", "name": "Cryptocium"},
    "@Dereserchinvestment": {"tier": 2, "type": "analysis", "name": "Cryptopouuse"},
    "@gpmeducation": {"tier": 2, "type": "analysis", "name": "GPM Trading Education"},
    "@trade4living_id": {"tier": 2, "type": "analysis", "name": "Trade4Living"},
    "@tradingtown": {"tier": 2, "type": "analysis", "name": "Trading Town"},
    "@cryptooverdose": {"tier": 2, "type": "analysis", "name": "Overdoze Crypto"},
    "@simbacryptogrup": {"tier": 2, "type": "analysis", "name": "Simba Crypto"},
    "@JURNALTRADE_OFICIAL": {"tier": 2, "type": "analysis", "name": "Jurnal Trade"},
    "@ceritatradingoneway": {"tier": 2, "type": "analysis", "name": "Cerita Trading"},
    1698558457: {"tier": 2, "type": "analysis", "name": "TumbuhKaya"},
    "@TheFomoLabs": {"tier": 2, "type": "analysis", "name": "TheFomoLabs"},
    "@tradewithsvnday": {"tier": 2, "type": "analysis", "name": "Trade With Svnday"},
    "@CryptoMonk_Japan": {"tier": 2, "type": "analysis", "name": "Crypto Monk"},
    "@Crptopouuse": {"tier": 2, "type": "analysis", "name": "Pouuse Grup"},
    "@SupXPload": {"tier": 2, "type": "analysis", "name": "IndoTraderXpert"},

    # ══════════════════════════════════════════════════════════
    # TIER 3: News channels (market sentiment context)
    # ══════════════════════════════════════════════════════════
    "@cointelegraph": {"tier": 3, "type": "news", "name": "Cointelegraph"},
    "@saillytradinggroup": {"tier": 3, "type": "news", "name": "Sailly Trading"},
    "@AshCryptoTG": {"tier": 3, "type": "news", "name": "Ash Crypto"},
    "@SM_News_24h": {"tier": 3, "type": "news", "name": "SM News"},
    "@cryptocurrency_media": {"tier": 3, "type": "news", "name": "Crypto News"},
    1685592361: {"tier": 3, "type": "news", "name": "Crypto News ID"},
    "@Analisa_Crypto": {"tier": 3, "type": "news", "name": "Analisa Crypto"},
    "@cryptocircle_id": {"tier": 3, "type": "news", "name": "Crypto Circle"},
    2201476957: {"tier": 3, "type": "news", "name": "Mikro Makro Ekonomi"},
}

# SUPPORTED_PAIRS → kept as a seed cache only.
# The bot now accepts ANY /USDT pair that has real OHLCV data on the exchange.
# New pairs from signals are automatically validated via _is_pair_tradeable().
SUPPORTED_PAIRS = {
    "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "DOT", "MATIC",
    "LINK", "LTC", "SUI", "ARB", "OP", "APT", "SEI", "TIA", "INJ", "FET",
    "RENDER", "WIF", "PEPE", "BONK", "FLOKI", "SHIB", "NEAR", "ATOM", "FTM",
    "ALGO", "HBAR", "XLM", "UNI", "AAVE", "MKR", "CRV", "LDO", "ONDO",
    "ENA", "JUP", "W", "STRK", "ZRO", "EIGEN", "MOODENG", "1000LUNC",
    "MTL", "SPX", "BAT", "STORJ", "MORPHO", "PIPPIN",
    "BCH", "ETC", "FIL", "RUNE", "SAND", "MANA", "GALA", "AXS",
    "IMX", "GMT", "APE", "BLUR", "ORDI", "1000PEPE", "1000BONK",
    "1000FLOKI", "1000SHIB", "DYDX", "SNX", "COMP", "GRT", "THETA",
    "VET", "ICP", "ROSE", "CELO", "KAVA", "ZEC", "NEO", "XTZ",
    "IOTA", "ONE", "ENS", "CHZ", "MASK", "YFI", "BAL", "SUSHI",
    "1INCH", "ANKR", "SSV", "ID", "RDNT", "PENDLE",
    "WLD", "CYBER", "ARKM", "NTRN", "PYTH", "JTO", "DYM", "PIXEL",
    "PORTAL", "ETHFI", "BOME", "MEW", "BB", "IO", "ZK",
    "LISTA", "BLAST", "NOT", "DOGS", "HMSTR", "CATI", "SCR",
    "MOVE", "USUAL", "PENGU", "VANA", "ME",
    # Extra pairs seen in signal channels
    "ENSO", "BIO", "KERNEL", "KITE", "NIGHT", "INIT", "HOOK",
    "LQTY", "API3", "LEVER", "BIGTIME", "HOOK", "TRB", "MAGIC",
    "PERP", "FLOW", "CFX", "STMX", "HIGH", "SXP", "LAZIO",
}

# Dynamic pair tradability cache: {pair_symbol: (is_tradeable: bool, timestamp)}
_pair_tradeable_cache: dict = {}

# Filter words — skip these messages (results, promotions, etc.)
SKIP_PATTERNS = [
    r"take.profit.*target.*\d+.*✅",      # TP result posts
    r"hit.*✅.*profit",                    # Hit TP result
    r"profit.*\d+%.*✅",                   # Profit announcement
    r"congratulations",
    r"join.*vip\s*[👉:@]",                # VIP promotion
    r"join.*premium",
    r"free.*for.*\d+.*minutes",            # Time-limited promo
    r"lucky.*draw",
    r"bonus.*\$?\d+",
    r"t\.me/\+[A-Za-z0-9]",               # Invite links (promo)
    r"(?:youtube|youtu\.be)/",             # YouTube links
    r"next.*signal.*👆",                   # "Next signal above" promo
    r"results?\s*:",                       # Results announcement
    r"pnl\s*:",
    r"closed.*profit",
]
SKIP_RE = [re.compile(p, re.IGNORECASE) for p in SKIP_PATTERNS]


class RealtimeSignalMonitor:
    """
    Event-driven real-time Telegram signal monitor.
    Listens to all configured channels, instantly processes new messages.
    """

    def __init__(self, starting_balance: float = 50.0, use_ta: bool = True,
                 max_leverage: int = 20):
        from telethon import TelegramClient, events
        from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

        # PID lock to prevent multiple instances
        self.pid_file = "realtime_monitor.pid"
        self._check_and_create_lock()

        self.api_id = int(os.getenv("TELEGRAM_API_ID", "0"))
        self.api_hash = os.getenv("TELEGRAM_API_HASH", "")
        self.phone = os.getenv("TELEGRAM_PHONE", "")

        # ── Session: StringSession (Railway/Cloud) vs file session (local dev) ──
        # StringSession eliminates AuthKeyDuplicatedError on redeploys:
        # Telegram will gracefully terminate the old connection when new one starts.
        session_string = os.getenv("TELEGRAM_SESSION_STRING", "")
        if session_string:
            session = StringSession(session_string)
            logger.info("✅ Using StringSession from env (Railway mode)")
        else:
            session = "futures_agent_session"  # File session for local dev
            logger.info("📁 Using file session (local dev mode)")

        self.client = TelegramClient(session, self.api_id, self.api_hash)
        self.use_ta = use_ta
        self.max_leverage = max_leverage
        self.running = True

        # Trading engine components (lazy init)
        self._market = None
        self._ta = None
        self._db = None
        self._analyzer = None
        self._parser = None
        self._consensus_validator = None
        self._news_correlator = None

        self.starting_balance = starting_balance

        # State
        self.news_context = {"sentiment": "NEUTRAL", "events": [], "updated": None}
        self.news_buffer: List[Dict] = []
        self.signals_processed = 0
        self.signals_executed = 0
        self.signals_skipped = 0
        self.start_time = datetime.now()
        self.state_file = "realtime_state.json"
        self.bot_update_offset = 0  # For Telegram Bot API polling

        # Position limits
        self.max_positions = 3
        self.risk_per_trade = 0.10     # 10% risk per trade
        self.margin_per_trade = 0.35   # 35% max margin per trade
        self.max_drawdown = 0.30       # 30% max drawdown → pause trading
        self.consecutive_losses = 0
        self.peak_balance = starting_balance

        # Processed message IDs
        self.processed_ids: Set[str] = set()
        self._load_state()

        # Channel entity cache (id → config)
        self._channel_map: Dict[int, Dict] = {}

        sig_module.signal(sig_module.SIGINT, self._graceful_shutdown)
        sig_module.signal(sig_module.SIGTERM, self._graceful_shutdown)

    def _graceful_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        sig_name = "SIGINT" if signum == sig_module.SIGINT else "SIGTERM"
        logger.info(f"Received {sig_name}, shutting down gracefully...")
        self.running = False

    # ─── Lazy component init ────────────────────────────
    @property
    def market(self):
        if not self._market:
            from market_data import MarketData
            self._market = MarketData()
        return self._market

    @property
    def ta(self):
        if not self._ta:
            from technical import TechnicalAnalyzer
            self._ta = TechnicalAnalyzer()
        return self._ta

    @property
    def db(self):
        if not self._db:
            from trade_db import TradeDB
            self._db = TradeDB("realtime_trades.db", self.starting_balance)
        return self._db

    @property
    def analyzer(self):
        if not self._analyzer:
            from chart_analyzer import ChartAnalyzer
            self._analyzer = ChartAnalyzer()
        return self._analyzer

    @property
    def parser(self):
        if not self._parser:
            from signal_scraper import SignalParser
            self._parser = SignalParser()
        return self._parser

    @property
    def consensus_validator(self):
        if not self._consensus_validator:
            from consensus_validator import ConsensusValidator
            self._consensus_validator = ConsensusValidator()
        return self._consensus_validator

    @property
    def news_correlator(self):
        if not self._news_correlator:
            from news_correlator import NewsCorrelator
            self._news_correlator = NewsCorrelator()
        return self._news_correlator

    @property
    def autonomous_engine(self):
        """Lazy-initialized autonomous trading engine."""
        if not hasattr(self, '_autonomous_engine') or self._autonomous_engine is None:
            from autonomous_engine import AutonomousEngine
            self._autonomous_engine = AutonomousEngine(
                market=self.market,
                db=self.db,
                tg_send_fn=tg_send,
                max_positions=self.max_positions,
            )
        return self._autonomous_engine

    # ─── PID Lock Management ───────────────────────────
    def _check_and_create_lock(self):
        """Check if another instance is running, create lock file."""
        if os.path.exists(self.pid_file):
            try:
                with open(self.pid_file, "r") as f:
                    old_pid = int(f.read().strip())
                # Check if process is actually running
                try:
                    os.kill(old_pid, 0)  # Signal 0 just checks if process exists
                    logger.error(f"Another instance is already running (PID {old_pid})")
                    logger.error(f"Stop it first with: kill {old_pid}")
                    sys.exit(1)
                except OSError:
                    # Process doesn't exist, remove stale lock
                    logger.warning(f"Removing stale lock file (PID {old_pid} not running)")
                    os.remove(self.pid_file)
            except (ValueError, FileNotFoundError):
                pass

        # Create new lock file
        with open(self.pid_file, "w") as f:
            f.write(str(os.getpid()))
        logger.info(f"Created PID lock: {os.getpid()}")

    def _remove_lock(self):
        """Remove PID lock file."""
        try:
            if os.path.exists(self.pid_file):
                os.remove(self.pid_file)
                logger.info("Removed PID lock")
        except Exception as e:
            logger.warning(f"Could not remove lock: {e}")

    # ─── State persistence ──────────────────────────────
    def _load_state(self):
        try:
            with open(self.state_file, "r") as f:
                state = json.load(f)
                self.start_time = datetime.fromisoformat(state.get("start_time", datetime.now().isoformat()))
                self.consecutive_losses = state.get("consecutive_losses", 0)
                self.peak_balance = state.get("peak_balance", self.starting_balance)
                self.signals_processed = state.get("signals_processed", 0)
                self.signals_executed = state.get("signals_executed", 0)
                self.signals_skipped = state.get("signals_skipped", 0)
                self.processed_ids = set(state.get("processed_ids", [])[-1000:])
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            self.start_time = datetime.now()

    def _save_state(self):
        with open(self.state_file, "w") as f:
            json.dump({
                "start_time": self.start_time.isoformat(),
                "consecutive_losses": self.consecutive_losses,
                "peak_balance": self.peak_balance,
                "signals_processed": self.signals_processed,
                "signals_executed": self.signals_executed,
                "signals_skipped": self.signals_skipped,
                "processed_ids": list(self.processed_ids)[-1000:],
            }, f, indent=2)

    # ─── Main entry point ────────────────────────────────
    async def run(self):
        """Start the real-time monitoring loop."""
        logger.info("=" * 60)
        logger.info("  REAL-TIME SIGNAL MONITOR STARTING")
        logger.info("=" * 60)

        # ── Connect: StringSession handles redeploy gracefully (no AuthKeyDuplicatedError) ──
        # With StringSession, Telegram terminates old connection when new one starts.
        # With file session (local dev), fall back to retry logic.
        from telethon.errors import AuthKeyDuplicatedError as _AuthKeyDuplicated
        session_string = os.getenv("TELEGRAM_SESSION_STRING", "")
        if session_string:
            # StringSession: connect directly, no retry needed
            await self.client.connect()
        else:
            # File session (local): retry if old instance still holding session
            max_connect_attempts = 5
            for attempt in range(max_connect_attempts):
                try:
                    await self.client.connect()
                    break
                except _AuthKeyDuplicated:
                    if attempt < max_connect_attempts - 1:
                        wait_secs = 15
                        logger.warning(
                            f"⚠️  AuthKeyDuplicatedError: Old session alive "
                            f"(attempt {attempt + 1}/{max_connect_attempts}). "
                            f"Waiting {wait_secs}s..."
                        )
                        await asyncio.sleep(wait_secs)
                        try:
                            await self.client.disconnect()
                        except Exception:
                            pass
                        self.client = TelegramClient(
                            "futures_agent_session", self.api_id, self.api_hash
                        )
                    else:
                        logger.error("❌ AuthKeyDuplicatedError: Too many retries. Use StringSession.")
                        raise

        if not await self.client.is_user_authorized():
            logger.error("Telegram not authorized. Run telegram_login.py first.")
            return

        me = await self.client.get_me()
        logger.info(f"Logged in as: {me.first_name} (@{me.username})")

        # Resolve channel entities and build channel map
        await self._build_channel_map()

        # Register event handler for ALL monitored channels
        # Use entities directly for more reliable matching
        chats = [config["entity"] for config in self._channel_map.values()]
        if not chats:
            logger.error("No channels resolved. Check SIGNAL_CHANNELS config.")
            return

        from telethon import events
        @self.client.on(events.NewMessage(chats=chats))
        async def on_new_message(event):
            await self._handle_message(event)

        logger.info(f"Monitoring {len(chats)} channels in real-time")
        logger.info(f"Balance: ${self.db.balance:.2f} | Max leverage: {self.max_leverage}x")
        logger.info(f"TA confirmation: {'ON' if self.use_ta else 'OFF'}")
        logger.info(f"Anti-liquidation: max {self.max_positions} positions, "
                     f"{self.max_drawdown*100:.0f}% max drawdown")
        logger.info("Waiting for signals...")
        logger.info("=" * 60)

        equity = self.db.get_equity()
        tg_send(
            f"<b>REAL-TIME MONITOR STARTED</b>\n"
            f"Channels: {len(chats)}\n"
            f"Balance: ${equity:.2f}\n"
            f"Max leverage: {self.max_leverage}x\n"
            f"TA: {'ON' if self.use_ta else 'OFF'}\n"
            f"🤖 Autonomous: {'ON' if os.getenv('ENABLE_AUTONOMOUS','true').lower()=='true' else 'OFF'} "
            f"(scan every {os.getenv('AUTONOMOUS_SCAN_INTERVAL_MIN','15')}min)\n"
            f"Waiting for signals..."
        )

        # Start background tasks
        monitor_task = asyncio.create_task(self._position_monitor_loop())
        dashboard_task = asyncio.create_task(self._dashboard_loop())
        news_task = asyncio.create_task(self._news_analysis_loop())
        bot_command_task = asyncio.create_task(self._bot_command_poller())

        # Autonomous market scan loop (runs independently of Telegram signals)
        enable_autonomous = os.getenv("ENABLE_AUTONOMOUS", "true").lower() == "true"
        autonomous_interval = int(os.getenv("AUTONOMOUS_SCAN_INTERVAL_MIN", "15"))
        if enable_autonomous:
            auto_task = asyncio.create_task(
                self.autonomous_engine.run_scan_loop(interval_minutes=autonomous_interval)
            )
            logger.info(f"🤖 Autonomous engine started (interval={autonomous_interval}min)")
        else:
            auto_task = None
            logger.info("🤖 Autonomous engine DISABLED (set ENABLE_AUTONOMOUS=true to enable)")

        try:
            # Keep running until stopped
            while self.running:
                await asyncio.sleep(1)
        except (asyncio.CancelledError, KeyboardInterrupt):
            logger.info("Received stop signal")
        except Exception as e:
            if "AuthKeyDuplicatedError" in str(type(e)):
                logger.error("Session stolen by another instance (AuthKeyDuplicatedError). Terminating old instance gracefully.")
            else:
                logger.error(f"Unexpected error in main loop: {e}")
        finally:
            self.running = False
            tasks = [monitor_task, dashboard_task, news_task, bot_command_task]
            if auto_task:
                tasks.append(auto_task)
            for task in tasks:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            self._save_state()
            self._print_final_report()
            await self.client.disconnect()
            self._remove_lock()

    async def _build_channel_map(self):
        """Resolve all channel entities and build ID → config mapping."""
        for key, config in SIGNAL_CHANNELS.items():
            try:
                if isinstance(key, int):
                    # Autocorrect positive integer channel IDs to Telegram's -100 format
                    if key > 0:
                        test_keys = [int(f"-100{key}"), key]
                    else:
                        test_keys = [key]
                        
                    entity = None
                    last_err = None
                    for t_key in test_keys:
                        try:
                            entity = await self.client.get_entity(t_key)
                            break
                        except Exception as e:
                            last_err = e
                            
                    if not entity:
                        logger.warning(f"  Could not resolve channel ID {key} ({config['name']}): {last_err}")
                        continue
                else:
                    entity = await self.client.get_entity(key)

                # Use get_peer_id to get the "marked" ID that matches event.chat_id
                # Channels: -100XXXXXXXXXX, Users: positive, Chats: negative
                from telethon.utils import get_peer_id
                eid = get_peer_id(entity)
                title = getattr(entity, 'title', str(key))
                config["entity"] = entity
                config["title"] = title
                self._channel_map[eid] = config
                logger.info(f"  + {config['tier']}:{config['type']:8} {title}")
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.warning(f"  Could not resolve {key}: {e}")

    # ─── Message handler (event-driven) ──────────────────
    async def _handle_message(self, event):
        """Handle incoming message from monitored channel."""
        try:
            chat_id = event.chat_id
            msg = event.message
            msg_key = f"{chat_id}_{msg.id}"
            
            # Debug log to catch ALL events
            logger.info(f"EVENT from {chat_id}: {msg.text[:50] if msg.text else 'media'}")


            # Skip already processed
            if msg_key in self.processed_ids:
                return
            self.processed_ids.add(msg_key)

            # Get channel config
            config = self._channel_map.get(chat_id)
            if not config:
                return

            text = msg.text or ""
            channel_name = config.get("title", str(chat_id))
            channel_type = config.get("type", "signal")
            tier = config.get("tier", 3)

            # Skip empty messages
            if not text and not msg.media:
                return

            # Skip promotional/result messages
            if text and self._is_skip_message(text):
                logger.debug(f"  SKIP (promo/result): [{channel_name}] {text[:80]}")
                return

            self.signals_processed += 1

            # Download image if present
            images = []
            from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
            if msg.media:
                if isinstance(msg.media, (MessageMediaPhoto, MessageMediaDocument)):
                    img_path = await self._download_image(msg, channel_name)
                    if img_path:
                        images.append(img_path)

            logger.info(f"NEW [{channel_name}] {text[:120]}{'...' if len(text) > 120 else ''}")

            # Route based on channel type
            if channel_type == "signal" and tier == 1:
                # TIER 1: Try direct parsing first (structured signals)
                await self._process_structured_signal(text, images, channel_name, config)
            elif channel_type == "analysis":
                # TIER 2: AI analysis needed
                await self._process_analysis_message(text, images, channel_name, config)
            elif channel_type == "news":
                # TIER 3: Queue for sentiment analysis
                self.news_buffer.append({
                    "text": text, "channel": channel_name,
                    "timestamp": datetime.now().isoformat()
                })
                if len(self.news_buffer) > 50:
                    self.news_buffer = self.news_buffer[-30:]
            else:
                # Unknown type — try AI analysis
                await self._process_analysis_message(text, images, channel_name, config)

            self._save_state()

        except Exception as e:
            logger.error(f"Message handler error: {e}")

    def _is_skip_message(self, text: str) -> bool:
        """Check if message should be skipped (promo, result, spam)."""
        for pattern in SKIP_RE:
            if pattern.search(text):
                return True
        # Skip very short messages (< 15 chars, usually chatter)
        if len(text.strip()) < 15:
            return True
        return False

    async def _download_image(self, msg, channel_name: str) -> Optional[bytes]:
        """Download image from message as bytes (not saved to disk)."""
        try:
            from io import BytesIO

            # Download to memory instead of disk
            buffer = BytesIO()
            await self.client.download_media(msg, file=buffer)

            image_bytes = buffer.getvalue()
            if image_bytes:
                logger.debug(f"Downloaded image from {channel_name} ({len(image_bytes)} bytes)")
                return image_bytes

        except Exception as e:
            logger.debug(f"Image download error: {e}")
        return None

    # ─── Bot Command Polling ────────────────────────────
    async def _bot_command_poller(self):
        """Poll Telegram Bot API for commands (background task)."""
        if not BOT_TOKEN:
            logger.warning("Bot token not configured, command polling disabled")
            return

        logger.info(f"Bot command polling started (BOT_TOKEN configured)")

        while self.running:
            try:
                # Long polling with 30s timeout
                updates = await asyncio.to_thread(tg_get_updates, self.bot_update_offset, 30)

                for update in updates:
                    self.bot_update_offset = update["update_id"] + 1

                    # Extract message
                    message = update.get("message", {})
                    if not message:
                        continue

                    text = message.get("text", "").strip()
                    chat_id = str(message.get("chat", {}).get("id", ""))

                    # Only process messages from authorized chat
                    if CHAT_ID and chat_id != CHAT_ID:
                        continue

                    # Process command
                    if text.startswith("/"):
                        logger.info(f"Bot command received: {text}")
                        await self._handle_bot_command(text)

            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f"Bot command poller error: {e}")
                await asyncio.sleep(5)

    async def _handle_bot_command(self, text: str):
        """Handle bot commands from user."""
        try:
            command = text.split()[0].lower()

            if command == "/help":
                help_text = (
                    "<b>Available Commands:</b>\n\n"
                    "/balance - Show current balance\n"
                    "/status - Show trading status\n"
                    "/positions - Show open positions\n"
                    "/stats - Show statistics\n"
                    "/signal LONG BTC 69000 TP 71000 SL 68000 - Manual signal\n"
                    "/signal_limit LONG BTC 69000 TP 71000 SL 68000 - Limit order\n"
                    "/pending - View pending limit orders\n"
                    "/cancel_limit 123 - Cancel limit order\n"
                    "/trending - View trending coins\n"
                    "/research [COIN] - Trigger AI research\n"
                    "/autoscan - Trigger immediate autonomous market scan\n"
                    "/autostatus - Show autonomous engine statistics\n"
                    "/channels - List monitored channels\n"
                    "/help - Show this help"
                )
                tg_send(help_text)

            elif command == "/autoscan":
                tg_send("🤖 <b>Running autonomous market scan...</b>")
                try:
                    results = await self.autonomous_engine.scan_all_pairs()
                    if results:
                        msg = f"🤖 <b>Autonomous scan complete</b>\n{len(results)} trade(s) opened"
                    else:
                        status = self.autonomous_engine.get_status()
                        msg = (
                            f"🤖 <b>Autonomous scan complete</b>\n"
                            f"No high-confluence setups found\n"
                            f"Min confluence required: {status['min_confluence']}/100"
                        )
                    tg_send(msg)
                except Exception as e:
                    tg_send(f"❌ Autonomous scan error: {e}")

            elif command == "/autostatus":
                try:
                    status = self.autonomous_engine.get_status()
                    msg = (
                        f"🤖 <b>Autonomous Engine Status</b>\n"
                        f"Pairs monitored: {status['pairs_monitored']}\n"
                        f"Total scans: {status['scans']}\n"
                        f"Setups found: {status['setups_found']}\n"
                        f"Auto trades: {status['auto_trades']}\n"
                        f"Min confluence: {status['min_confluence']}/100\n"
                        f"Scan interval: {os.getenv('AUTONOMOUS_SCAN_INTERVAL_MIN', '15')}min"
                    )
                    tg_send(msg)
                except Exception as e:
                    tg_send(f"❌ Auto status error: {e}")

            elif command == "/balance":
                stats = self.db.get_stats()
                equity = self.db.get_equity()
                balance = stats["balance"]
                start_bal = stats["starting_balance"]
                locked = self.db.get_locked_margin()
                open_pnl_approx = equity - balance - locked
                roi = (equity - start_bal) / start_bal * 100 if start_bal > 0 else 0
                pnl = stats["total_pnl"]

                msg = (
                    f"<b>Balance</b>\n"
                    f"Current: ${equity:.2f}\n"
                    f"  └ Realized: ${balance:.2f}\n"
                    f"  └ Locked margin: ${locked:.2f}\n"
                    f"Start: ${start_bal:.2f}\n"
                    f"P&L (realized): ${pnl:+.2f}\n"
                    f"ROI: {roi:+.1f}%"
                )
                tg_send(msg)

            elif command == "/status":
                stats = self.db.get_stats()
                equity = self.db.get_equity()
                start_bal = stats["starting_balance"]
                roi = (equity - start_bal) / start_bal * 100 if start_bal > 0 else 0
                elapsed = datetime.now() - self.start_time
                hours = elapsed.total_seconds() / 3600

                msg = (
                    f"<b>Trading Status</b>\n"
                    f"Balance: ${equity:.2f} (ROI: {roi:+.1f}%)\n"
                    f"Runtime: {hours:.1f}h\n"
                    f"Trades: {stats['total_trades']} (W:{stats['wins']} L:{stats['losses']})\n"
                    f"Win Rate: {stats['win_rate']:.1f}%\n"
                    f"Open: {stats['open_positions']}/{self.max_positions}\n"
                    f"Signals: {self.signals_processed} seen, {self.signals_executed} traded\n"
                    f"News: {self.news_context.get('sentiment', 'NEUTRAL')}\n"
                    f"Loss streak: {self.consecutive_losses}"
                )
                tg_send(msg)

            elif command == "/positions":
                open_trades = self.db.get_open_trades()
                if not open_trades:
                    tg_send("No open positions")
                    return

                msg = f"<b>Open Positions ({len(open_trades)})</b>\n\n"
                for t in open_trades:
                    price = self.market.get_current_price(t["symbol"])
                    if price:
                        if t["side"] == "LONG":
                            pnl = (price - t["entry_price"]) / t["entry_price"] * 100 * t["leverage"]
                        else:
                            pnl = (t["entry_price"] - price) / t["entry_price"] * 100 * t["leverage"]

                        msg += (
                            f"#{t['id']} {t['side']} {t['symbol']}\n"
                            f"Entry: ${t['entry_price']:,.4f}\n"
                            f"Current: ${price:,.4f}\n"
                            f"P&L: {pnl:+.1f}%\n"
                            f"Leverage: {t['leverage']}x\n"
                            f"SL: ${t['stop_loss']:,.4f}\n\n"
                        )
                tg_send(msg)

            elif command == "/stats":
                stats = self.db.get_stats()
                equity = self.db.get_equity()
                locked = self.db.get_locked_margin()
                start_bal = stats["starting_balance"]
                roi = (equity - start_bal) / start_bal * 100 if start_bal > 0 else 0
                elapsed = datetime.now() - self.start_time

                msg = (
                    f"<b>Statistics</b>\n"
                    f"Balance: ${start_bal:.2f} → ${equity:.2f}\n"
                    f"  Realized: ${stats['balance']:.2f} | Locked: ${locked:.2f}\n"
                    f"Total P&L (realized): ${stats['total_pnl']:+.2f}\n"
                    f"ROI: {roi:+.1f}%\n"
                    f"Peak: ${self.peak_balance:.2f}\n\n"
                    f"Trades: {stats['total_trades']}\n"
                    f"Wins: {stats['wins']}\n"
                    f"Losses: {stats['losses']}\n"
                    f"Win Rate: {stats['win_rate']:.1f}%\n\n"
                    f"Runtime: {elapsed}\n"
                    f"Signals processed: {self.signals_processed}\n"
                    f"Signals executed: {self.signals_executed}\n"
                    f"Signals skipped: {self.signals_skipped}"
                )
                tg_send(msg)

            elif command == "/channels":
                msg = f"<b>Monitored Channels ({len(SIGNAL_CHANNELS)})</b>\n\n"
                for key, cfg in SIGNAL_CHANNELS.items():
                    msg += f"T{cfg['tier']} {cfg['type']:8} {cfg['name']}\n"
                tg_send(msg)

            elif command == "/signal":
                # Manual signal: /signal LONG BTC 69000 TP 71000 SL 68000
                signal_text = text[7:].strip()  # Remove "/signal"
                if not signal_text:
                    tg_send("Usage: /signal LONG BTC 69000 TP 71000 SL 68000")
                    return

                parsed = self.parser.parse(signal_text)
                if parsed:
                    parsed["source"] = "manual"
                    success = await self._execute_trade(parsed, "manual_command")
                    if success:
                        tg_send("✅ Signal executed")
                    else:
                        tg_send("❌ Signal rejected (check logs)")
                else:
                    tg_send("Could not parse signal. Example:\n/signal LONG BTC 69000 TP 71000 SL 68000")

            elif command == "/signal_limit":
                # Limit order: /signal_limit LONG BTC 69000 TP 71000 SL 68000
                signal_text = text[13:].strip()  # Remove "/signal_limit"
                if not signal_text:
                    tg_send("Usage: /signal_limit LONG BTC 69000 TP 71000 SL 68000")
                    return

                parsed = self.parser.parse(signal_text)
                if parsed:
                    parsed["source"] = "manual_limit"
                    parsed["is_limit"] = True
                    # Create limit order via database
                    try:
                        result = self.db.create_limit_order(parsed)
                        order_id = result.get("id")
                        tg_send(f"📌 Limit order created #{order_id}\n{parsed['side']} {parsed['pair']} @ {parsed.get('entry', 'market')}\nWill execute when price is reached")
                    except Exception as e:
                        tg_send(f"❌ Error creating limit order: {e}")
                else:
                    tg_send("Could not parse signal. Example:\n/signal_limit LONG BTC 69000 TP 71000 SL 68000")

            elif command == "/pending":
                # Show pending limit orders
                orders = self.db.get_pending_limit_orders()
                if not orders:
                    tg_send("📋 No pending limit orders")
                else:
                    msg = f"<b>Pending Limit Orders ({len(orders)})</b>\n\n"
                    for o in orders[:10]:
                        icon = "🟢" if o["side"] == "LONG" else "🔴"
                        msg += f"{icon} #{o['id']} {o['side']} {o['symbol']}\n"
                        msg += f"   Entry: ${o['entry_price']:,.4f}\n"
                        msg += f"   Leverage: {o.get('leverage', 1)}x\n"
                        msg += f"   SL: ${o.get('stop_loss', 'N/A')}\n"
                        msg += f"   Created: {o.get('created_at', '?')[:16]}\n\n"
                    if len(orders) > 10:
                        msg += f"... and {len(orders) - 10} more\n"
                    msg += "\nUse /cancel_limit <id> to cancel"
                    tg_send(msg)

            elif command == "/cancel_limit":
                # Cancel limit order: /cancel_limit 123
                try:
                    parts = text.split()
                    if len(parts) < 2:
                        tg_send("Usage: /cancel_limit 123")
                        return
                    order_id = int(parts[1])
                    success = self.db.cancel_limit_order(order_id)
                    if success:
                        tg_send(f"✅ Order #{order_id} cancelled")
                    else:
                        tg_send(f"❌ Order #{order_id} not found or already executed")
                except ValueError:
                    tg_send("Usage: /cancel_limit 123 (order ID must be a number)")

            elif command == "/trending":
                # Show trending coins
                try:
                    from trending_tracker import TrendingTracker
                    tracker = TrendingTracker()
                    trending = tracker.scan_trending()
                    
                    if not trending:
                        tg_send("🔍 No trending coins detected")
                    else:
                        msg = f"<b>Trending Coins ({len(trending)})</b>\n\n"
                        for t in trending[:10]:
                            icon = "🔥" if t.get('price_change_24h', 0) > 0 else "📉"
                            msg += f"{icon} {t['symbol']}\n"
                            msg += f"   Score: {t.get('final_score', 0):.1f}/10\n"
                            msg += f"   Sources: {t.get('sources', 'N/A')}\n"
                            if t.get('price'):
                                msg += f"   Price: ${t['price']:,.4f}\n"
                            if t.get('price_change_24h') is not None:
                                msg += f"   24h: {t['price_change_24h']:+.2f}%\n\n"
                        tg_send(msg)
                except Exception as e:
                    tg_send(f"❌ Error getting trending: {e}")

            elif command == "/research":
                # Trigger AI research: /research or /research BTC
                try:
                    from ai_research_agent import AIResearchAgent
                    agent = AIResearchAgent()
                    
                    # Check if specific coin requested
                    parts = text.split()
                    if len(parts) > 1:
                        coin = parts[1].upper()
                        tg_send(f"🔬 Researching {coin}...")
                        signal = agent.manual_research(coin)
                    else:
                        tg_send("🔬 Running AI research cycle...")
                        signals = agent.run_research_cycle()
                        signal = signals[0] if signals else None
                    
                    if signal:
                        msg = f"✅ AI Research Result:\n"
                        msg += f"{signal.get('action', 'SKIP')} {signal.get('symbol', '?')}\n"
                        msg += f"Confidence: {signal.get('confidence', 0):.0%}\n"
                        msg += f"Reasoning: {signal.get('reasoning', 'N/A')[:100]}"
                        tg_send(msg)
                    else:
                        tg_send("No high-confidence signal generated")
                except Exception as e:
                    tg_send(f"❌ Error: {e}")

            else:
                tg_send(f"Unknown command: {command}\nSend /help for available commands")

        except Exception as e:
            logger.error(f"Bot command handler error: {e}")
            tg_send(f"Error: {e}")

    # ─── Dynamic Pair Validation ────────────────────────────
    async def _is_pair_tradeable(self, pair: str) -> bool:
        """
        Dynamically check if a pair is tradeable by verifying live candle data exists.
        Replaces the static SUPPORTED_PAIRS whitelist.
        Results cached for 1 hour to avoid repeated API calls.

        Accepts: 'ENSO/USDT', 'ENSO', '#ENSO', 'enso', 'ENSO/USDT:USDT'
        Rejects: Forex (XAUUSD), pairs with no data, malformed symbols
        """
        import time as _time

        # Normalise pair to BASE/USDT format
        raw = pair.strip().lstrip("#").upper()
        raw = raw.split(":")[0]  # strip ":USDT" perpetual suffix
        raw = raw.replace(" ", "").replace("-", "")

        # Skip obvious non-crypto: XAUUSD, EURUSD, etc.
        FIAT_KEYWORDS = {"XAU", "EUR", "GBP", "JPY", "USD/", "FOREX", "GOLD", "OIL", "SPX500"}
        for fk in FIAT_KEYWORDS:
            if fk in raw:
                return False

        # Normalise to BASE/USDT
        if "/" not in raw:
            raw = raw.replace("USDT", "")
            symbol = f"{raw}/USDT"
        else:
            symbol = raw if raw.endswith("/USDT") else raw.split("/")[0] + "/USDT"

        # Check cache (TTL 1 hour)
        cached = _pair_tradeable_cache.get(symbol)
        if cached is not None:
            result, ts = cached
            if _time.time() - ts < 3600:
                return result

        # Fast-path: already in known seed set
        base = symbol.replace("/USDT", "")
        if base in SUPPORTED_PAIRS:
            _pair_tradeable_cache[symbol] = (True, _time.time())
            return True

        # Live check: try fetching 5m candles (just 5 bars)
        try:
            df = await asyncio.to_thread(self.market.get_candles, symbol, "5m", 5)
            is_ok = df is not None and not df.empty and len(df) >= 3
        except Exception:
            is_ok = False

        _pair_tradeable_cache[symbol] = (is_ok, _time.time())
        if is_ok:
            logger.info(f"  ✓ Pair {symbol} validated dynamically — added to tradeable set")
            SUPPORTED_PAIRS.add(base)  # Cache for future lookups
        else:
            logger.debug(f"  ✗ Pair {symbol} not tradeable (no exchange data)")
        return is_ok

    # ─── Signal Processing ─────────────────────────────────
    async def _process_structured_signal(self, text: str, images: List[str],
                                          channel_name: str, config: Dict):
        """Process a TIER 1 structured signal (entry/TP/SL format)."""
        # Try direct parsing with SignalParser
        parsed = self.parser.parse(text)

        if parsed:
            # Dynamic validation: verify the pair has live data (not static whitelist)
            tradeable = await self._is_pair_tradeable(parsed["pair"])
            if not tradeable:
                logger.info(f"  SKIP: {parsed['pair']} has no exchange data")
                self.signals_skipped += 1
                return

            logger.info(f"  PARSED: {parsed['side']} {parsed['pair']} "
                        f"entry={parsed.get('entry')} TP={parsed.get('targets')} SL={parsed.get('stop_loss')}")

            # Execute
            success = await self._execute_trade(parsed, channel_name)
            if success:
                self.signals_executed += 1
            else:
                self.signals_skipped += 1
        else:
            # Fallback: AI analysis
            await self._process_analysis_message(text, images, channel_name, config)

    async def _process_analysis_message(self, text: str, images: List[str],
                                         channel_name: str, config: Dict):
        """Process TIER 2 analysis message with AI."""
        message = {
            "text": text,
            "images": images,
            "channel": channel_name,
        }

        # Run AI analysis (Groq for text, Gemini for images)
        try:
            result = self.analyzer.analyze_message(message)
        except Exception as e:
            logger.error(f"Analyzer error in {channel_name}: {e}")
            self.signals_skipped += 1
            return

        if not result or not isinstance(result, dict):
            self.signals_skipped += 1
            return

        # If it's news, buffer it
        if result.get("is_news"):
            self.news_buffer.append({
                "text": text, "channel": channel_name,
                "timestamp": datetime.now().isoformat(),
                "sentiment": result.get("news_sentiment", "NEUTRAL"),
            })
            logger.info(f"  NEWS: {result.get('news_sentiment', '?')} from {channel_name}")
            return

        # If it's a signal
        if result.get("side") and result.get("pair"):
            raw_conf = result.get("confidence", 0)
            # BUG FIX #3: Cap confidence ke 0-1 (AI bisa return 70.0 = 7000%)
            confidence = max(0.0, min(1.0, float(raw_conf) if raw_conf else 0.0))
            # Tier 1 (structured): accept at 0.45+. Tier 2 (AI analysis): 0.50+
            min_conf = 0.50 if config.get("tier") == 2 else 0.45
            if confidence < min_conf:
                logger.info(f"  LOW CONF: {result['side']} {result['pair']} conf={confidence:.0%} < {min_conf:.0%}")
                self.signals_skipped += 1
                return

            # Dynamic validation: check if exchange has data for this pair
            tradeable = await self._is_pair_tradeable(result["pair"])
            if not tradeable:
                logger.info(f"  SKIP: {result['pair']} has no exchange data (unlisted pair)")
                self.signals_skipped += 1
                return

            signal = {
                "pair": result["pair"],
                "side": result["side"],
                "entry": result.get("entry"),
                "targets": result.get("targets", []),
                "stop_loss": result.get("stop_loss"),
                "leverage": result.get("leverage"),
                "confidence": confidence,
                "source": f"ai:{channel_name}",
            }

            logger.info(f"  AI SIGNAL: {signal['side']} {signal['pair']} conf={confidence:.0%}")

            success = await self._execute_trade(signal, channel_name)
            if success:
                self.signals_executed += 1
            else:
                self.signals_skipped += 1
        else:
            self.signals_skipped += 1

    # ─── Trade Execution ────────────────────────────────────
    async def _execute_trade(self, signal: Dict, source: str) -> bool:
        """Execute a trade signal with all safeguards."""
        pair = signal["pair"]
        side = signal["side"]

        # Clean pair format
        if "/" not in pair:
            pair = pair.replace("USDT", "/USDT")
        if not pair.endswith("/USDT"):
            pair += "/USDT"
        pair = pair.replace("/USDT/USDT", "/USDT")

        # ─── Pre-trade checks ───────────────────────────
        # 1. Max positions check
        open_trades = self.db.get_open_trades()
        if len(open_trades) >= self.max_positions:
            logger.info(f"  REJECT: Max {self.max_positions} positions reached")
            return False

        # 2. Already have position in this pair?
        if any(t["symbol"] == pair for t in open_trades):
            logger.info(f"  REJECT: Already have position in {pair}")
            return False

        # 3. Drawdown check — use equity (realized balance + open margin)
        balance = self.db.balance
        equity = self.db.get_equity()  # balance + locked margin in open positions
        drawdown = (self.peak_balance - equity) / self.peak_balance if self.peak_balance > 0 else 0
        if drawdown > self.max_drawdown:
            logger.info(f"  REJECT: Drawdown {drawdown:.0%} exceeds {self.max_drawdown:.0%} limit")
            return False

        # 4. Loss streak cooldown
        if self.consecutive_losses >= 4:
            logger.info(f"  REJECT: {self.consecutive_losses} consecutive losses, cooling down")
            return False

        # 5. Minimum balance check
        if balance < 5:
            logger.info(f"  REJECT: Balance ${balance:.2f} too low")
            return False

        # ─── Get price ────────────────────────────────────
        price = self.market.get_current_price(pair)
        if not price:
            logger.info(f"  REJECT: No price for {pair}")
            return False

        # 6. Entry proximity check (if entry price specified)
        # Allow configurable tolerance via environment variable
        max_entry_deviation = float(os.getenv("MAX_ENTRY_DEVIATION_PCT", "5.0"))

        entry = signal.get("entry")
        if entry and entry > 0:
            entry_diff = abs(price - entry) / entry * 100

            # ── BUG FIX: BIO/USDT catastrophic loss ──
            # Signal entry=$398 (parsed wrong from text), actual price=$0.0379
            # entry_diff = 99.6% → bot buka, langsung SL kena, rugi -800%
            # Fix: HARD REJECT jika entry vs market price > 50%
            if entry_diff > 50.0:
                logger.info(
                    f"  REJECT: Signal entry ${entry:,.4f} vs market ${price:,.4f} "
                    f"({entry_diff:.1f}% deviation — price mismatch, likely wrong parse)"
                )
                return False

            if entry_diff > max_entry_deviation:
                logger.info(f"  REJECT: Price ${price:,.4f} too far from entry ${entry:,.4f} ({entry_diff:.1f}% > {max_entry_deviation}%)")
                return False

        # ─── Multi-AI Consensus Validation ────────────────
        # Only run if enabled in environment
        enable_consensus = os.getenv("ENABLE_AI_CONSENSUS", "false").lower() == "true"

        if enable_consensus:
            try:
                consensus_result = self.consensus_validator.validate_signal(
                    signal=signal,
                    context={
                        "technical": {},  # Will be filled by TA below
                        "market": {
                            "price": price,
                            "pair": pair,
                        },
                        "news": self.news_context.get("summary", "")
                    }
                )

                if not consensus_result:
                    logger.info(f"  REJECT: Multi-AI consensus rejected signal")
                    return False

                # Update signal with consensus data
                signal = consensus_result
                logger.info(f"  ✓ Consensus: {signal.get('confidence', 0.0):.2f} confidence")
            except Exception as e:
                logger.error(f"  Consensus validation error: {e}")
                # Continue without consensus if it fails
                pass

        # ─── Real-Time News Correlation ───────────────────
        # Only run if enabled in environment
        enable_news = os.getenv("ENABLE_NEWS_CORRELATION", "false").lower() == "true"

        if enable_news:
            try:
                news_corr = self.news_correlator.correlate_signal(signal)

                if news_corr.get("should_skip"):
                    logger.info(f"  REJECT: Breaking news contradicts {side} signal")
                    logger.info(f"    News: {news_corr.get('news_summary', '')}")
                    return False

                # Adjust confidence based on news
                conf_adjustment = news_corr.get("confidence_adjustment", 0.0)
                if conf_adjustment != 0:
                    old_conf = signal.get("confidence", 0.5)
                    signal["confidence"] = max(0.0, min(1.0, old_conf + conf_adjustment))
                    logger.info(f"  News adjustment: {old_conf:.2f} → {signal['confidence']:.2f} ({conf_adjustment:+.2f})")
            except Exception as e:
                logger.error(f"  News correlation error: {e}")
                # Continue without news correlation if it fails
                pass

        # ─── TA confirmation (soft filter) ──────────────────
        # TA adjusts leverage/confidence but does NOT hard-reject channel signals.
        # Only hard-reject if TA STRONGLY disagrees (configurable threshold).
        ta_score = 50
        ta_penalty = 1.0  # Multiplier for leverage (1.0 = no penalty)
        if self.use_ta:
            ta_agrees, ta_score = self._ta_confirmation(pair, side)
            # Hard reject threshold: only block if TA score is extreme
            # LONG: reject only if score < 30 (strong bearish)
            # SHORT: reject only if score > 70 (strong bullish)
            hard_reject_threshold = float(os.getenv("TA_HARD_REJECT_THRESHOLD", "30"))
            if side == "LONG" and ta_score < hard_reject_threshold:
                logger.info(f"  REJECT: TA strongly disagrees (score={ta_score:.0f} < {hard_reject_threshold:.0f})")
                return False
            elif side == "SHORT" and ta_score > (100 - hard_reject_threshold):
                logger.info(f"  REJECT: TA strongly disagrees (score={ta_score:.0f} > {100 - hard_reject_threshold:.0f})")
                return False

            if not ta_agrees:
                # Soft penalty: reduce leverage when TA mildly disagrees
                ta_penalty = 0.6
                logger.info(f"  TA mild disagree (score={ta_score:.0f}), reducing leverage")
            else:
                logger.info(f"  TA confirms {side} (score={ta_score:.0f})")

        # ─── News sentiment boost/penalty ─────────────────
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

        # ─── Calculate levels ─────────────────────────────
        sl = signal.get("stop_loss")
        targets = signal.get("targets", [])

        # Compute SL if not provided
        if not sl:
            candles_5m = self.market.get_candles(pair, "5m", 50)
            if candles_5m is not None and not candles_5m.empty:
                from technical import atr as calc_atr
                atr_val = calc_atr(candles_5m["high"], candles_5m["low"], candles_5m["close"], 14).iloc[-1]
            else:
                atr_val = price * 0.01
            sl_distance = atr_val * 1.5
            sl = price - sl_distance if side == "LONG" else price + sl_distance

        sl_dist_pct = abs(price - sl) / price * 100

        # Safety: reject if SL is more than 5%
        if sl_dist_pct > 5.0:
            logger.info(f"  REJECT: SL too far ({sl_dist_pct:.1f}% > 5% limit)")
            return False

        # Compute TPs if not provided
        if not targets or len(targets) == 0:
            sl_dist = abs(price - sl)
            if side == "LONG":
                targets = [price + sl_dist * 1.5, price + sl_dist * 2.5, price + sl_dist * 4]
            else:
                targets = [price - sl_dist * 1.5, price - sl_dist * 2.5, price - sl_dist * 4]

        # ─── Leverage calculation ─────────────────────────
        sig_leverage = signal.get("leverage")
        leverage = sig_leverage or self._calc_leverage(sl_dist_pct, ta_score)
        # Apply TA penalty (reduces leverage when TA mildly disagrees)
        leverage = max(1, int(leverage * ta_penalty))
        leverage = min(leverage, self.max_leverage)

        # ─── Position sizing ──────────────────────────────
        pos = self._calc_position(price, sl_dist_pct, leverage)
        if not pos:
            return False

        # ─── Open trade ───────────────────────────────────
        tp1 = targets[0] if len(targets) > 0 else None
        tp2 = targets[1] if len(targets) > 1 else None
        tp3 = targets[2] if len(targets) > 2 else None

        # Fallback TPs
        if not tp1:
            tp1 = price * (1.02 if side == "LONG" else 0.98)
        if not tp2:
            tp2 = price * (1.04 if side == "LONG" else 0.96)
        if not tp3:
            tp3 = price * (1.06 if side == "LONG" else 0.94)

        # ── BUG FIX: Mencegah Buka Posisi Jika Market Sudah Mencapai Max TP ──
        # Jika bot menerima sinyal namun harga saat dieksekusi sudah berada di harga TP max
        # maka langsung batalkan / close entry (jangan dibuka)
        max_tp = tp3 if tp3 else tp2
        if max_tp:
            if side == "LONG" and price >= max_tp * 0.995: # 0.5% tolerance
                logger.info(f"  REJECT: Market price ${price:,.4f} sudah berada di max TP ${max_tp:,.4f}. Batal entry.")
                return False
            elif side == "SHORT" and price <= max_tp * 1.005:
                logger.info(f"  REJECT: Market price ${price:,.4f} sudah berada di max TP ${max_tp:,.4f}. Batal entry.")
                return False

        trade = {
            "symbol": pair, "side": side, "action": side,
            "entry_price": price, "quantity": pos["quantity"],
            "leverage": leverage, "margin": pos["margin"],
            "position_value": pos["value"],
            "stop_loss": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
            "sl_pct": sl_dist_pct,
            "confidence": signal.get("confidence", 0.6),
            "reasoning": f"RT signal from {source} | TA={ta_score:.0f} | News={news_sentiment}",
            "model": "RT_SIGNAL",
            "ta_score": ta_score,
        }

        result = self.db.open_trade(trade)
        trade_id = result.get("id") if isinstance(result, dict) else result

        if trade_id:
            logger.info(
                f"  OPENED #{trade_id}: {side} {pair} @ ${price:,.4f} | "
                f"{leverage}x | margin ${pos['margin']:.2f} | SL ${sl:,.4f} | TP1 ${tp1:,.4f}"
            )
            tg_send(
                f"<b>TRADE OPENED</b>\n"
                f"{side} {pair} @ ${price:,.4f}\n"
                f"Leverage: {leverage}x | Margin: ${pos['margin']:.2f}\n"
                f"SL: ${sl:,.4f} ({sl_dist_pct:.1f}%)\n"
                f"TP1: ${tp1:,.4f} | TP2: ${tp2:,.4f}\n"
                f"Source: {source}"
            )
            return True

        return False

    def _ta_confirmation(self, pair: str, side: str) -> tuple:
        """Check if TA agrees with signal direction."""
        candles = self.market.get_multi_timeframe(pair)
        if len(candles) < 1:
            return True, 50

        result = self.ta.multi_timeframe_analysis(candles)
        score = result.get("consensus_score", 50)

        if side == "LONG":
            return score >= 45, score
        else:
            return score <= 55, score

    def _calc_leverage(self, sl_dist_pct: float, ta_score: float) -> int:
        """Calculate leverage aggressively with SL-based safety cap."""
        strength = abs(ta_score - 50) / 50
        if strength > 0.6:
            base = 20
        elif strength > 0.4:
            base = 15
        elif strength > 0.2:
            base = 10
        else:
            base = 8

        # SL-based safety: leverage * SL < 25% max loss
        safety_max = int(25 / max(sl_dist_pct, 0.1))

        leverage = min(base, safety_max, self.max_leverage)
        return max(2, leverage)

    def _calc_position(self, price: float, sl_dist_pct: float,
                       leverage: int) -> Optional[Dict]:
        """Calculate position size for paper trading."""
        balance = self.db.balance

        risk_amount = balance * self.risk_per_trade

        if sl_dist_pct > 0:
            position_value = risk_amount / (sl_dist_pct / 100)
        else:
            position_value = risk_amount * 10

        max_position = balance * leverage
        position_value = min(position_value, max_position)

        margin = position_value / leverage
        if margin > balance * self.margin_per_trade:
            margin = balance * self.margin_per_trade
            position_value = margin * leverage

        quantity = position_value / price

        if margin < 1 or margin > balance:
            logger.info(f"  REJECT: margin=${margin:.2f} invalid (balance=${balance:.2f})")
            return None

        return {
            "margin": round(margin, 2),
            "value": round(position_value, 2),
            "quantity": round(quantity, 6),
        }

    # ─── Background tasks ──────────────────────────────────
    async def _position_monitor_loop(self):
        """Monitor open positions every 10 seconds for SL/TP and pending limit orders."""
        while self.running:
            try:
                await asyncio.sleep(10)
                
                # Check pending limit orders first
                pending_opts = self.db.get_pending_limit_orders()
                for order in pending_opts:
                    await self._check_limit_order(order)
                    
                open_trades = self.db.get_open_trades()
                for trade in open_trades:
                    self._check_position(trade)
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                await asyncio.sleep(5)

    async def _check_limit_order(self, order: Dict):
        """Check if pending limit order price is reached to execute trade."""
        try:
            price = self.market.get_current_price(order["symbol"])
            if not price:
                return

            side = order["side"]
            entry_price = float(order["entry_price"])
            
            # For LONG: Execute if market price drops to or below limit entry
            # For SHORT: Execute if market price rises to or above limit entry
            execute = False
            if side == "LONG" and price <= entry_price:
                execute = True
            elif side == "SHORT" and price >= entry_price:
                execute = True
                
            if execute:
                logger.info(f"  LIMIT HIT: {side} {order['symbol']} reached entry {entry_price:,.4f} at market {price:,.4f}")
                
                parsed = {
                    "pair": order["symbol"],
                    "side": side,
                    "entry": entry_price, # Let it enter at limit price
                    "targets": [order.get("tp1"), order.get("tp2"), order.get("tp3")],
                    "stop_loss": order.get("stop_loss"),
                    "leverage": order.get("leverage")
                }
                
                self.db.cancel_limit_order(order["id"])
                
                # Increase tolerance specifically for limit orders since it executes exactly at the limit price
                prev_tol = os.environ.get("MAX_ENTRY_DEVIATION_PCT", "5.0")
                os.environ["MAX_ENTRY_DEVIATION_PCT"] = "100.0"
                
                success = await self._execute_trade(parsed, "LIMIT_TRIGGER")
                
                os.environ["MAX_ENTRY_DEVIATION_PCT"] = prev_tol
                
                if not success:
                    logger.warning(f"Failed to execute limit order #{order['id']}")
                    tg_send(f"❌ Limit order #{order['id']} for {order['symbol']} triggered but failed to execute.")
                
        except Exception as e:
            logger.error(f"Limit order check error #{order.get('id', '?')}: {e}")

    def _check_position(self, trade: Dict):
        """Check a single position for SL/TP."""
        try:
            price = self.market.get_current_price(trade["symbol"])
            if not price:
                return

            side = trade["side"]
            entry = trade["entry_price"]
            sl = trade["stop_loss"]
            tp1 = trade["tp1"]
            tp2 = trade.get("tp2", tp1 * (1.02 if side == "LONG" else 0.98))
            tp3 = trade.get("tp3", tp2 * (1.02 if side == "LONG" else 0.98))

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

            # ── BUG FIX: TP2/TP3 harus langsung CLOSE, bukan hanya geser SL ──
            # Sebelumnya: TP2 hit -> hanya geser SL ke entry -> harga balik -> close kecil
            # Contoh: ESP +38% leveraged, bisa dapat besar, malah close +1.8% karena SL
            if hit_tp3:
                self._close_trade(trade, price, "TP3", leveraged_pnl)
            elif hit_tp2:
                # TP2 hit → CLOSE TRADE langsung (profit terjamin)
                self._close_trade(trade, price, "TP2", leveraged_pnl)
            elif hit_tp1:
                # TP1 hit → hanya geser SL ke entry (trailing stop, break-even)
                new_sl = entry
                if (side == "LONG" and new_sl > sl) or (side == "SHORT" and new_sl < sl):
                    self.db.update_stop_loss(trade["id"], new_sl)
                    logger.info(f"  #{trade['id']} TP1 hit → SL moved to entry ${entry:,.4f}")
            elif hit_sl:
                self._close_trade(trade, price, "SL", leveraged_pnl)
            elif leveraged_pnl < -20:
                self._close_trade(trade, price, "EMERGENCY_SL", leveraged_pnl)
            elif leveraged_pnl >= 30:
                # Auto-close jika profit >= 30% leveraged (take profit agresif)
                # Mencegah profit besar balik menjadi loss seperti kasus ESP
                self._close_trade(trade, price, "AUTO_TP", leveraged_pnl)

        except Exception as e:
            logger.error(f"Position check error #{trade.get('id', '?')}: {e}")

    def _close_trade(self, trade: Dict, price: float, reason: str, pnl_pct: float):
        """Close a trade."""
        result = self.db.close_trade(trade["id"], price, reason)
        profit = result.get("profit", 0) if isinstance(result, dict) else 0

        if profit >= 0:
            self.consecutive_losses = 0
            self.peak_balance = max(self.peak_balance, self.db.get_equity())
        else:
            self.consecutive_losses += 1

        emoji = "+" if profit >= 0 else "-"
        logger.info(
            f"  CLOSED #{trade['id']}: {trade['side']} {trade['symbol']} | "
            f"{reason} | P&L: ${profit:+.2f} ({pnl_pct:+.1f}%)"
        )
        tg_send(
            f"{'WIN' if profit >= 0 else 'LOSS'} <b>TRADE CLOSED</b>\n"
            f"{trade['side']} {trade['symbol']} @ ${price:,.4f}\n"
            f"Reason: {reason}\n"
            f"P&L: ${profit:+.2f} ({pnl_pct:+.1f}%)\n"
            f"Balance: ${self.db.balance:.2f}"
        )

    async def _dashboard_loop(self):
        """Print dashboard every 60 seconds."""
        while self.running:
            try:
                await asyncio.sleep(60)
                self._print_dashboard()
            except asyncio.CancelledError:
                return
            except Exception:
                await asyncio.sleep(30)

    async def _news_analysis_loop(self):
        """Analyze buffered news every 5 minutes."""
        while self.running:
            try:
                await asyncio.sleep(300)  # 5 minutes
                if self.news_buffer:
                    self.news_context = self.analyzer.analyze_news_context(self.news_buffer)
                    self.news_context["updated"] = datetime.now().isoformat()
                    sentiment = self.news_context.get("sentiment", "NEUTRAL")
                    logger.info(f"  NEWS UPDATE: {sentiment} ({len(self.news_buffer)} msgs)")
                    # Keep last 20 for next cycle
                    self.news_buffer = self.news_buffer[-20:]
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f"News analysis error: {e}")
                await asyncio.sleep(60)

    # ─── Dashboard ──────────────────────────────────────────
    def _print_dashboard(self):
        """Log compact dashboard."""
        stats = self.db.get_stats()
        open_trades = self.db.get_open_trades()
        elapsed = datetime.now() - self.start_time
        hours = elapsed.total_seconds() / 3600
        equity = self.db.get_equity()
        start_bal = stats["starting_balance"]
        roi = (equity - start_bal) / start_bal * 100 if start_bal > 0 else 0

        logger.info("─" * 50)
        logger.info(f"DASHBOARD | {hours:.1f}h | ${equity:.2f} (ROI: {roi:+.1f}%) | realized=${stats['balance']:.2f}")
        logger.info(f"  Trades: {stats['total_trades']} | W:{stats['wins']} L:{stats['losses']} | WR: {stats['win_rate']:.0f}%")
        logger.info(f"  Signals: {self.signals_processed} processed, {self.signals_executed} executed, {self.signals_skipped} skipped")
        logger.info(f"  News: {self.news_context.get('sentiment', '?')} | Losses streak: {self.consecutive_losses}")

        for t in open_trades:
            price = self.market.get_current_price(t["symbol"])
            if price:
                if t["side"] == "LONG":
                    pnl = (price - t["entry_price"]) / t["entry_price"] * 100 * t["leverage"]
                else:
                    pnl = (t["entry_price"] - price) / t["entry_price"] * 100 * t["leverage"]
                logger.info(f"  #{t['id']} {t['side']:5} {t['symbol']:10} {t['leverage']:2}x | {pnl:+.2f}%")

        logger.info("─" * 50)

    def _print_final_report(self):
        """Print final report."""
        stats = self.db.get_stats()
        elapsed = datetime.now() - self.start_time
        balance = stats["balance"]
        start_bal = stats["starting_balance"]
        roi = (balance - start_bal) / start_bal * 100 if start_bal > 0 else 0

        report = (
            f"\n{'='*50}\n"
            f"  REAL-TIME MONITOR — FINAL REPORT\n"
            f"{'='*50}\n"
            f"  Duration:        {elapsed}\n"
            f"  Start balance:   ${start_bal:.2f}\n"
            f"  Final balance:   ${balance:.2f}\n"
            f"  ROI:             {roi:+.2f}%\n"
            f"  Total PnL:       ${stats['total_pnl']:+.2f}\n"
            f"  Trades:          {stats['total_trades']}\n"
            f"  Win Rate:        {stats['win_rate']:.1f}%\n"
            f"  Peak Balance:    ${self.peak_balance:.2f}\n"
            f"  Signals seen:    {self.signals_processed}\n"
            f"  Signals traded:  {self.signals_executed}\n"
            f"  Signals skipped: {self.signals_skipped}\n"
            f"{'='*50}\n"
        )
        print(report)
        logger.info(report)
        tg_send(
            f"<b>REAL-TIME MONITOR STOPPED</b>\n"
            f"Balance: ${start_bal:.2f} -> ${balance:.2f}\n"
            f"ROI: {roi:+.2f}%\n"
            f"Trades: {stats['total_trades']} | WR: {stats['win_rate']:.1f}%\n"
            f"Duration: {elapsed}"
        )


# ─── CLI ────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Real-Time Telegram Signal Monitor")
    parser.add_argument("--reset", action="store_true", help="Reset state and DB")
    parser.add_argument("--balance", type=float, default=50.0, help="Starting balance (default: $50)")
    parser.add_argument("--no-ta", action="store_true", help="Disable TA confirmation")
    parser.add_argument("--max-leverage", type=int, default=20, help="Max leverage (default: 20)")
    parser.add_argument("--status", action="store_true", help="Show current status")
    parser.add_argument("--list-channels", action="store_true", help="List monitored channels")
    args = parser.parse_args()

    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    if args.reset:
        for f in ["realtime_trades.db", "realtime_state.json", "realtime_debug.log"]:
            try:
                os.remove(f)
            except FileNotFoundError:
                pass
        print("Reset complete.")

    if args.list_channels:
        print(f"\nMonitored channels ({len(SIGNAL_CHANNELS)}):")
        for key, cfg in SIGNAL_CHANNELS.items():
            print(f"  T{cfg['tier']} {cfg['type']:8} {cfg['name']}")
        return

    if args.status:
        try:
            from trade_db import TradeDB
            db = TradeDB("realtime_trades.db", args.balance)
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

    monitor = RealtimeSignalMonitor(
        starting_balance=args.balance,
        use_ta=not args.no_ta,
        max_leverage=args.max_leverage,
    )

    try:
        def handle_sigterm(signum, frame):
            logger.info("Received stop signal (SIGTERM/SIGINT) - shutting down gracefully...")
            monitor.running = False
            # We raise KeyboardInterrupt to exit the asyncio event loop cleanly
            raise KeyboardInterrupt()

        # Register signal handlers for graceful shutdown on Railway redeploys
        sig_module.signal(sig_module.SIGTERM, handle_sigterm)
        sig_module.signal(sig_module.SIGINT, handle_sigterm)

        asyncio.run(monitor.run())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt - exiting")
    except Exception as e:
        if "AuthKeyDuplicatedError" in str(type(e)):
            logger.error("❌ AuthKeyDuplicatedError persists even after retry. Another instance may be stuck — exiting.")
        else:
            logger.error(f"Fatal error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
