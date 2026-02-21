"""
Generate Telegram StringSession for Railway deployment.
Run this script ONCE locally, then copy the session string to Railway env vars.

Usage:
    python generate_session_string.py

It will print a long string like:
    1BVtsOJ8Bu2...

Copy that string and set it as TELEGRAM_SESSION_STRING in Railway.
"""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    api_id = int(os.getenv("TELEGRAM_API_ID", "0"))
    api_hash = os.getenv("TELEGRAM_API_HASH", "")
    phone = os.getenv("TELEGRAM_PHONE", "")

    if not api_id or not api_hash:
        print("❌ TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in .env")
        return

    print(f"Connecting as {phone}...")
    print("You will receive an OTP on Telegram/SMS.\n")

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start(phone=phone)

    session_string = client.session.save()

    print("\n" + "=" * 60)
    print("✅ SESSION STRING GENERATED SUCCESSFULLY!")
    print("=" * 60)
    print("\nCopy the string below and set it as TELEGRAM_SESSION_STRING")
    print("in Railway → Service → Variables:\n")
    print(session_string)
    print("\n" + "=" * 60)
    print("⚠️  KEEP THIS STRING SECRET — it grants full Telegram access!")
    print("=" * 60)

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
