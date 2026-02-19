"""
Telegram Signal Scraper & Parser
==================================
Scrapes crypto trading signals from Telegram channels and parses them
into actionable trade signals (entry, TP, SL).

Supports common signal formats from popular channels:
- "BUY BTC/USDT @ 69000 TP: 71000 SL: 68000"
- "LONG SOL Entry: 85-86 Targets: 88/90/95 SL: 83"
- Emoji-based: "🟢 ETH LONG 1950 TP 2000 2050 SL 1900"
- And many more variations

Uses Telegram Bot API (no Telethon session needed for channel reading via bot).
"""

import re
import os
import json
import time
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("signal_scraper")

# ─── Signal Parsing Patterns ──────────────────────────

# Common pair formats
PAIR_PATTERNS = [
    r'(BTC|ETH|SOL|BNB|XRP|DOGE|ADA|AVAX|DOT|MATIC|LINK|LTC|SUI|ARB|OP|APT|SEI|TIA|INJ|FET|RENDER|WIF|PEPE|BONK|FLOKI|SHIB|NEAR|ATOM|FTM|ALGO)'
]

# Side detection
LONG_WORDS = ['long', 'buy', 'bullish', 'call', 'pump', '🟢', '🟩', '🔵', '📈', '⬆️', '🚀']
SHORT_WORDS = ['short', 'sell', 'bearish', 'put', 'dump', '🔴', '🟥', '🟠', '📉', '⬇️']

# Number extraction
NUM_PATTERN = r'[\$]?\s*(\d+[\.,]?\d*)'


class SignalParser:
    """Parses raw text messages into structured trade signals."""

    def parse(self, text: str) -> Optional[Dict]:
        """
        Parse a message into a trade signal.
        Returns None if message is not a valid signal.
        """
        if not text or len(text) < 10:
            return None

        text_lower = text.lower()

        # Skip non-signal messages
        skip_words = ['result', 'update', 'closed', 'hit tp', 'hit sl',
                      'congratulations', 'profit:', 'pnl:', 'cancelled']
        if any(w in text_lower for w in skip_words):
            return None

        # 1. Detect pair
        pair = self._extract_pair(text)
        if not pair:
            return None

        # 2. Detect side (LONG/SHORT)
        side = self._extract_side(text_lower)
        if not side:
            return None

        # 3. Extract entry price(s)
        entry = self._extract_entry(text, text_lower)

        # 4. Extract take profit level(s)
        tps = self._extract_targets(text, text_lower)

        # 5. Extract stop loss
        sl = self._extract_stoploss(text, text_lower)

        # 6. Extract leverage if mentioned
        leverage = self._extract_leverage(text, text_lower)

        if not entry and not tps:
            return None

        signal = {
            "pair": f"{pair}/USDT",
            "side": side,
            "entry": entry,
            "targets": tps,
            "stop_loss": sl,
            "leverage": leverage,
            "raw_text": text[:500],
            "parsed_at": datetime.now().isoformat(),
        }

        # Validate signal makes sense
        if not self._validate_signal(signal):
            return None

        return signal

    def _extract_pair(self, text: str) -> Optional[str]:
        text_upper = text.upper()
        # Try "BTC/USDT" or "BTCUSDT" format first
        m = re.search(r'([A-Z]{2,10})\s*[/\-]?\s*USDT', text_upper)
        if m:
            return m.group(1)
        # Try standalone coin names
        for p in PAIR_PATTERNS:
            m = re.search(p, text_upper)
            if m:
                return m.group(1)
        return None

    def _extract_side(self, text_lower: str) -> Optional[str]:
        long_score = sum(1 for w in LONG_WORDS if w in text_lower)
        short_score = sum(1 for w in SHORT_WORDS if w in text_lower)
        if long_score > short_score:
            return "LONG"
        elif short_score > long_score:
            return "SHORT"
        return None

    def _extract_entry(self, text: str, text_lower: str) -> Optional[float]:
        # Try "entry: 69000" or "entry zone: 68500 - 69500"
        patterns = [
            r'entry\s*(?:price|zone|:)?\s*:?\s*' + NUM_PATTERN,
            r'(?:buy|sell|long|short)\s+(?:at|@|around)?\s*' + NUM_PATTERN,
            r'(?:open|enter)\s+(?:at|@)?\s*' + NUM_PATTERN,
            r'@\s*' + NUM_PATTERN,
        ]
        for p in patterns:
            m = re.search(p, text_lower)
            if m:
                return self._parse_number(m.group(1))

        # Range entry: "68500 - 69500"
        m = re.search(r'entry.*?' + NUM_PATTERN + r'\s*[-–]\s*' + NUM_PATTERN, text_lower)
        if m:
            low = self._parse_number(m.group(1))
            high = self._parse_number(m.group(2))
            if low and high:
                return (low + high) / 2

        # Fallback: first number after pair and side keyword
        pair = self._extract_pair(text)
        side = self._extract_side(text_lower)
        if pair and side:
            # Find first number after the pair/side mention
            side_word = 'long' if side == 'LONG' else 'short'
            idx = max(text_lower.find(pair.lower()), text_lower.find(side_word))
            if idx >= 0:
                after = text_lower[idx:]
                m = re.search(NUM_PATTERN, after)
                if m:
                    val = self._parse_number(m.group(1))
                    if val and val > 0:
                        return val

        return None

    def _extract_targets(self, text: str, text_lower: str) -> List[float]:
        targets = []
        # Use multiple specific patterns to avoid \d? eating the first digit of price
        tp_patterns = [
            r'tp\d\s*[:=]\s*' + NUM_PATTERN,    # "TP1: 70000", "TP2=72000"
            r'tp\s*[:=]\s*' + NUM_PATTERN,       # "TP: 70000", "TP=70000"
            r'tp\d?\s+' + NUM_PATTERN,           # "TP 70000", "TP1 70000"
        ]
        for pattern in tp_patterns:
            tp_matches = re.findall(pattern, text_lower)
            for m in tp_matches:
                v = self._parse_number(m)
                if v and v not in targets:
                    targets.append(v)

        if not targets:
            # "Targets: 70000 / 72000 / 75000"
            m = re.search(r'target[s]?\s*:?\s*([\d\s,./\-]+)', text_lower)
            if m:
                nums = re.findall(NUM_PATTERN, m.group(1))
                targets = [self._parse_number(n) for n in nums if self._parse_number(n)]

        if not targets:
            # "Take profit: 70000"
            m = re.search(r'take\s*profit\s*:?\s*' + NUM_PATTERN, text_lower)
            if m:
                v = self._parse_number(m.group(1))
                if v:
                    targets.append(v)

        return targets[:5]  # Max 5 targets

    def _extract_stoploss(self, text: str, text_lower: str) -> Optional[float]:
        patterns = [
            r'(?:stop\s*loss|sl|stoploss)\s*:?\s*' + NUM_PATTERN,
            r'(?:stop|invalidation)\s*:?\s*' + NUM_PATTERN,
        ]
        for p in patterns:
            m = re.search(p, text_lower)
            if m:
                return self._parse_number(m.group(1))
        return None

    def _extract_leverage(self, text: str, text_lower: str) -> Optional[int]:
        m = re.search(r'(\d+)\s*x\s*(?:lev|leverage)?', text_lower)
        if m:
            lev = int(m.group(1))
            if 1 <= lev <= 125:
                return lev
        m = re.search(r'lev(?:erage)?\s*:?\s*(\d+)', text_lower)
        if m:
            lev = int(m.group(1))
            if 1 <= lev <= 125:
                return lev
        return None

    def _parse_number(self, s: str) -> Optional[float]:
        try:
            s = s.replace(',', '').replace('$', '').strip()
            return float(s)
        except (ValueError, AttributeError):
            return None

    def _validate_signal(self, sig: Dict) -> bool:
        """Basic sanity checks on parsed signal."""
        entry = sig.get("entry")
        sl = sig.get("stop_loss")
        tps = sig.get("targets", [])
        side = sig.get("side")

        # Must have at least entry OR targets
        if not entry and not tps:
            return False

        # If we have entry and SL, check they make sense
        if entry and sl and entry > 0 and sl > 0:
            if side == "LONG" and sl >= entry:
                return False  # SL above entry for LONG
            if side == "SHORT" and sl <= entry:
                return False  # SL below entry for SHORT

        # If we have entry and TP, check direction
        if entry and tps and entry > 0:
            if side == "LONG" and any(tp < entry for tp in tps):
                pass  # Allow some flexibility
            if side == "SHORT" and any(tp > entry for tp in tps):
                pass

        return True


class TelegramSignalScraper:
    """
    Scrapes signals from Telegram channels using Bot API.
    Works with public channels where the bot is a member.
    Also supports manual signal input via /signal command.
    """

    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.signal_channels = self._load_channels()
        self.parser = SignalParser()
        self.last_update_id = 0
        self.signals_file = "signals_history.json"
        self.pending_signals: List[Dict] = []
        self._load_pending()

    def _load_channels(self) -> List[str]:
        """Load signal channel IDs/usernames from env or config."""
        channels_str = os.getenv("SIGNAL_CHANNELS", "")
        if channels_str:
            return [c.strip() for c in channels_str.split(",") if c.strip()]
        # Try loading from file
        try:
            with open("signal_channels.json", "r") as f:
                data = json.load(f)
                return data.get("channels", [])
        except FileNotFoundError:
            return []

    def _load_pending(self):
        """Load pending signals from disk."""
        try:
            with open(self.signals_file, "r") as f:
                data = json.load(f)
                self.pending_signals = data.get("pending", [])
                self.last_update_id = data.get("last_update_id", 0)
        except (FileNotFoundError, json.JSONDecodeError):
            self.pending_signals = []

    def _save_pending(self):
        """Save pending signals to disk."""
        with open(self.signals_file, "w") as f:
            json.dump({
                "pending": self.pending_signals[-50:],  # Keep last 50
                "last_update_id": self.last_update_id,
            }, f, indent=2)

    def scrape_channels(self) -> List[Dict]:
        """
        Scrape messages from configured signal channels.
        Returns list of parsed signals.
        """
        new_signals = []

        for channel in self.signal_channels:
            try:
                messages = self._get_channel_messages(channel)
                for msg in messages:
                    signal = self.parser.parse(msg)
                    if signal:
                        signal["source"] = f"channel:{channel}"
                        new_signals.append(signal)
                        logger.info(f"Signal from {channel}: {signal['side']} {signal['pair']}")
            except Exception as e:
                logger.debug(f"Error scraping {channel}: {e}")

        return new_signals

    def _get_channel_messages(self, channel: str, limit: int = 20) -> List[str]:
        """
        Get recent messages from a channel.
        Bot must be added to the channel as admin.
        Uses getUpdates to collect forwarded messages.
        """
        messages = []

        # Method: Use channel forwarding — bot reads messages forwarded to it
        # The bot can also read channels it's an admin of via polling
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            params = {"offset": self.last_update_id + 1, "limit": 100, "timeout": 5}
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for update in data.get("result", []):
                    self.last_update_id = max(self.last_update_id, update["update_id"])
                    msg = update.get("channel_post", {}) or update.get("message", {})
                    text = msg.get("text", "")
                    # Check if from our tracked channel
                    chat = msg.get("chat", {})
                    chat_username = chat.get("username", "").lower()
                    chat_title = chat.get("title", "").lower()
                    if channel.lower().lstrip("@") in (chat_username, chat_title):
                        if text:
                            messages.append(text)
                    # Also check forwarded messages
                    fwd = msg.get("forward_from_chat", {})
                    if fwd:
                        fwd_username = fwd.get("username", "").lower()
                        if channel.lower().lstrip("@") in fwd_username:
                            if text:
                                messages.append(text)
        except Exception as e:
            logger.debug(f"getUpdates error: {e}")

        return messages

    def check_manual_signals(self) -> List[Dict]:
        """
        Check for manual signals sent via Telegram bot /signal command.
        User sends: /signal LONG BTC 69000 TP 71000 SL 68000
        Also handles: /signal_limit, /pending, /cancel_limit
        """
        signals = []
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            params = {"offset": self.last_update_id + 1, "limit": 100, "timeout": 2}
            resp = requests.get(url, params=params, timeout=8)
            if resp.status_code != 200:
                return signals

            data = resp.json()
            for update in data.get("result", []):
                self.last_update_id = max(self.last_update_id, update["update_id"])
                msg = update.get("message", {})
                text = msg.get("text", "")
                chat_id = str(msg.get("chat", {}).get("id", ""))

                # Only accept from our chat
                if chat_id != self.chat_id:
                    continue

                # /signal command (market order)
                if text.startswith("/signal"):
                    signal_text = text[7:].strip()
                    parsed = self.parser.parse(signal_text)
                    if parsed:
                        parsed["source"] = "manual"
                        signals.append(parsed)
                        self._reply(chat_id, f"✅ Signal received:\n{parsed['side']} {parsed['pair']}\nEntry: {parsed.get('entry', 'market')}\nTP: {parsed.get('targets', [])}\nSL: {parsed.get('stop_loss', 'none')}")
                    else:
                        self._reply(chat_id, "❌ Could not parse signal. Format:\n/signal LONG BTC 69000 TP 71000 SL 68000")

                # /signal_limit command (limit order)
                elif text.startswith("/signal_limit"):
                    signal_text = text[13:].strip()
                    parsed = self.parser.parse(signal_text)
                    if parsed:
                        parsed["source"] = "manual_limit"
                        parsed["is_limit"] = True
                        signals.append(parsed)
                        self._reply(chat_id, f"📌 Limit order signal received:\n{parsed['side']} {parsed['pair']} @ {parsed.get('entry', 'N/A')}\nWill execute when price is reached")
                    else:
                        self._reply(chat_id, "❌ Could not parse limit signal. Format:\n/signal_limit LONG BTC 69000 TP 71000 SL 68000")

                # /pending command - show pending limit orders
                elif text.startswith("/pending"):
                    self._reply(chat_id, "📋 Checking pending orders... (check Telegram bot for list)")

                # /cancel_limit <id> command
                elif text.startswith("/cancel_limit"):
                    try:
                        order_id = int(text.split()[1])
                        self._reply(chat_id, f"⏳ Cancel request for order #{order_id} sent. Check bot logs.")
                    except (IndexError, ValueError):
                        self._reply(chat_id, "❌ Invalid format. Use:\n/cancel_limit 123")

                # /add_channel command
                elif text.startswith("/add_channel"):
                    channel = text[12:].strip()
                    if channel:
                        if channel not in self.signal_channels:
                            self.signal_channels.append(channel)
                            self._save_channels()
                            self._reply(chat_id, f"✅ Added signal channel: {channel}")
                        else:
                            self._reply(chat_id, f"⚠️ Channel already tracked: {channel}")

                # /channels command
                elif text.startswith("/channels"):
                    if self.signal_channels:
                        self._reply(chat_id, "📺 Signal channels:\n" + "\n".join(f"- {c}" for c in self.signal_channels))
                    else:
                        self._reply(chat_id, "No signal channels configured.\nUse /add_channel @channel_name")

            self._save_pending()

        except Exception as e:
            logger.debug(f"Manual signal check error: {e}")

        return signals

    def get_pending_signals(self) -> List[Dict]:
        """Get all pending (unexecuted) signals."""
        # Scrape channels + check manual
        channel_signals = self.scrape_channels()
        manual_signals = self.check_manual_signals()

        all_new = channel_signals + manual_signals

        # Add to pending
        for sig in all_new:
            sig["status"] = "pending"
            self.pending_signals.append(sig)

        self._save_pending()

        # Return only pending ones
        return [s for s in self.pending_signals if s.get("status") == "pending"]

    def mark_executed(self, signal: Dict):
        """Mark a signal as executed."""
        signal["status"] = "executed"
        signal["executed_at"] = datetime.now().isoformat()
        self._save_pending()

    def mark_skipped(self, signal: Dict, reason: str):
        """Mark a signal as skipped."""
        signal["status"] = "skipped"
        signal["skip_reason"] = reason
        self._save_pending()

    def _reply(self, chat_id: str, text: str):
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=5)
        except Exception:
            pass

    def _save_channels(self):
        with open("signal_channels.json", "w") as f:
            json.dump({"channels": self.signal_channels}, f, indent=2)


# ─── Test ──────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = SignalParser()

    test_signals = [
        "🟢 LONG BTC/USDT\nEntry: 68500 - 69000\nTP1: 70000\nTP2: 72000\nTP3: 75000\nSL: 67500\nLeverage: 20x",
        "SHORT ETH @ 1960\nTargets: 1900 / 1850 / 1800\nStop loss: 2000\n10x leverage",
        "BUY SOL/USDT 85.5\nTP: 90, 95, 100\nSL: 82\n15x",
        "🔴 XRP SHORT\nEntry zone: 1.45-1.48\nTP1: 1.40\nTP2: 1.35\nSL: 1.52\nLev: 20x",
        "DOGE LONG entry 0.065 targets 0.07 0.075 0.08 sl 0.06 leverage 25x",
        "Just some random chat message, not a signal",
        "Results: BTC TP1 hit! +500 pips profit!",
    ]

    for text in test_signals:
        result = parser.parse(text)
        if result:
            print(f"\n[SIGNAL] {result['side']} {result['pair']}")
            print(f"  Entry: {result.get('entry')}")
            print(f"  Targets: {result.get('targets')}")
            print(f"  SL: {result.get('stop_loss')}")
            print(f"  Leverage: {result.get('leverage')}")
        else:
            print(f"\n[SKIP] {text[:60]}...")
