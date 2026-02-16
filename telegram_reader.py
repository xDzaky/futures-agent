"""
Telegram Channel Reader — Reads signals from crypto channels
================================================================
Uses Telethon (Telegram User API) to:
- Join and read public channels
- Download images/charts
- Extract text messages
- Monitor new posts in real-time

Requires: API ID + API Hash from https://my.telegram.org
"""

import os
import json
import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("tg_reader")

# Lazy import telethon (only when needed)
_telethon_available = False
try:
    from telethon import TelegramClient, events
    from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
    _telethon_available = True
except ImportError:
    pass


class TelegramChannelReader:
    """
    Reads messages from Telegram channels using Telethon.
    Supports text + image downloading.
    """

    def __init__(self):
        self.api_id = os.getenv("TELEGRAM_API_ID", "")
        self.api_hash = os.getenv("TELEGRAM_API_HASH", "")
        self.phone = os.getenv("TELEGRAM_PHONE", "")
        self.session_name = "futures_agent_session"

        # Channels to monitor
        self.channels = self._load_channels()

        # Message cache (avoid re-processing)
        self.processed_ids = set()
        self.messages_file = "channel_messages.json"
        self._load_processed()

        # Image download directory
        self.img_dir = os.path.join(os.path.dirname(__file__), "chart_images")
        os.makedirs(self.img_dir, exist_ok=True)

        self.client = None
        self._connected = False

    def _load_channels(self) -> List[str]:
        """Load channel list from config."""
        channels_str = os.getenv("SIGNAL_CHANNELS", "")
        channels = [c.strip() for c in channels_str.split(",") if c.strip()]

        # Also load from file
        try:
            with open("signal_channels.json", "r") as f:
                data = json.load(f)
                file_channels = data.get("channels", [])
                for c in file_channels:
                    if c not in channels:
                        channels.append(c)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        return channels

    def _load_processed(self):
        try:
            with open(self.messages_file, "r") as f:
                data = json.load(f)
                self.processed_ids = set(data.get("processed_ids", []))
        except (FileNotFoundError, json.JSONDecodeError):
            self.processed_ids = set()

    def _save_processed(self):
        # Keep last 500 IDs to prevent file growing forever
        ids = list(self.processed_ids)[-500:]
        with open(self.messages_file, "w") as f:
            json.dump({"processed_ids": ids}, f)

    def is_configured(self) -> bool:
        """Check if Telegram API credentials are configured."""
        return bool(self.api_id and self.api_hash and _telethon_available)

    async def _ensure_connected(self):
        """Connect to Telegram if not already connected."""
        if self._connected and self.client:
            return True

        if not self.is_configured():
            logger.warning("Telegram API not configured. Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env")
            return False

        try:
            self.client = TelegramClient(
                self.session_name,
                int(self.api_id),
                self.api_hash
            )
            await self.client.start(phone=self.phone if self.phone else None)
            self._connected = True
            logger.info("Connected to Telegram")
            return True
        except Exception as e:
            logger.error(f"Telegram connection failed: {e}")
            return False

    async def fetch_recent_messages(self, channel: str, limit: int = 20,
                                     hours_back: int = 4) -> List[Dict]:
        """
        Fetch recent messages from a channel.
        Returns list of {text, images, timestamp, channel, msg_id}
        """
        if not await self._ensure_connected():
            return []

        messages = []
        cutoff = datetime.utcnow() - timedelta(hours=hours_back)

        try:
            entity = await self.client.get_entity(channel)
            async for msg in self.client.iter_messages(entity, limit=limit):
                # Skip old messages
                if msg.date and msg.date.replace(tzinfo=None) < cutoff:
                    break

                # Skip already processed
                msg_key = f"{channel}_{msg.id}"
                if msg_key in self.processed_ids:
                    continue

                text = msg.text or ""
                images = []

                # Download images if present
                if msg.media:
                    if isinstance(msg.media, MessageMediaPhoto):
                        img_path = await self._download_media(msg, channel)
                        if img_path:
                            images.append(img_path)
                    elif isinstance(msg.media, MessageMediaDocument):
                        # Check if it's an image document
                        if msg.media.document and msg.media.document.mime_type:
                            if msg.media.document.mime_type.startswith("image/"):
                                img_path = await self._download_media(msg, channel)
                                if img_path:
                                    images.append(img_path)

                if text or images:
                    messages.append({
                        "text": text,
                        "images": images,
                        "timestamp": msg.date.isoformat() if msg.date else "",
                        "channel": channel,
                        "msg_id": msg.id,
                        "msg_key": msg_key,
                    })

                    self.processed_ids.add(msg_key)

        except Exception as e:
            logger.error(f"Error reading {channel}: {e}")

        self._save_processed()
        return messages

    async def _download_media(self, msg, channel: str) -> Optional[bytes]:
        """Download media from a message, return image bytes (not saved to disk)."""
        try:
            from io import BytesIO

            # Download to memory instead of disk
            buffer = BytesIO()
            await self.client.download_media(msg, file=buffer)

            image_bytes = buffer.getvalue()
            if image_bytes:
                logger.debug(f"Downloaded image from {channel} ({len(image_bytes)} bytes)")
                return image_bytes

        except Exception as e:
            logger.debug(f"Media download error: {e}")
        return None

    async def fetch_all_channels(self) -> List[Dict]:
        """Fetch recent messages from all configured channels."""
        all_messages = []
        for channel in self.channels:
            msgs = await self.fetch_recent_messages(channel)
            all_messages.extend(msgs)
            await asyncio.sleep(1)  # Rate limiting
        return all_messages

    def fetch_sync(self) -> List[Dict]:
        """Synchronous wrapper for fetch_all_channels."""
        if not self.is_configured():
            return []
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.fetch_all_channels())
        finally:
            loop.close()

    async def add_channel(self, channel: str) -> bool:
        """Add and join a channel."""
        if not await self._ensure_connected():
            return False
        try:
            # Try to join channel
            entity = await self.client.get_entity(channel)
            if channel not in self.channels:
                self.channels.append(channel)
                self._save_channels()
            logger.info(f"Added channel: {channel}")
            return True
        except Exception as e:
            logger.error(f"Could not add channel {channel}: {e}")
            return False

    def _save_channels(self):
        with open("signal_channels.json", "w") as f:
            json.dump({"channels": self.channels}, f, indent=2)

    async def disconnect(self):
        if self.client:
            await self.client.disconnect()
            self._connected = False


# ─── Test ──────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    reader = TelegramChannelReader()

    if reader.is_configured():
        print("Telegram API configured. Fetching messages...")
        msgs = reader.fetch_sync()
        for m in msgs:
            print(f"\n[{m['channel']}] {m['timestamp']}")
            print(f"  Text: {m['text'][:100]}...")
            print(f"  Images: {len(m['images'])}")
    else:
        print("Telegram API not configured.")
        print("Add to .env:")
        print("  TELEGRAM_API_ID=your_api_id")
        print("  TELEGRAM_API_HASH=your_api_hash")
        print("  TELEGRAM_PHONE=+62xxxxxxxxxx")
        print()
        print("Get credentials from: https://my.telegram.org")
