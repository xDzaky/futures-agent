"""
Telegram Login — One-time authentication for channel reading.
Run this ONCE to create a session file, then the bot can read channels automatically.

Usage:
    python3 telegram_login.py

You will be asked to enter the verification code sent to your Telegram app.
After successful login, a session file is created and you never need to login again.
"""

import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def main():
    api_id = os.getenv("TELEGRAM_API_ID", "")
    api_hash = os.getenv("TELEGRAM_API_HASH", "")
    phone = os.getenv("TELEGRAM_PHONE", "")

    if not api_id or not api_hash:
        print("ERROR: Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env")
        return

    print(f"API ID: {api_id}")
    print(f"Phone: {phone}")
    print()

    from telethon import TelegramClient

    client = TelegramClient("futures_agent_session", int(api_id), api_hash)

    await client.start(phone=phone)

    me = await client.get_me()
    print(f"\nLogged in as: {me.first_name} (@{me.username})")
    print(f"Session file created: futures_agent_session.session")

    # Test reading channels
    channels = ["@MWcryptojournal", "@binance_360"]
    for ch in channels:
        try:
            entity = await client.get_entity(ch)
            title = getattr(entity, 'title', ch)
            msgs = []
            async for msg in client.iter_messages(entity, limit=3):
                if msg.text:
                    msgs.append(msg.text[:80])
            print(f"\n[OK] {title} — {len(msgs)} recent messages:")
            for m in msgs:
                print(f"  > {m}...")
        except Exception as e:
            print(f"\n[FAIL] {ch}: {e}")

    await client.disconnect()
    print("\nDone! Session saved. The bot can now read channels automatically.")


if __name__ == "__main__":
    asyncio.run(main())
