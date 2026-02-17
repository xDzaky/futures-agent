"""List all Telegram channels/groups the user is part of."""
import os
import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat

load_dotenv()

api_id = int(os.getenv("TELEGRAM_API_ID", "0"))
api_hash = os.getenv("TELEGRAM_API_HASH", "")

async def main():
    client = TelegramClient("futures_agent_session", api_id, api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        print("Not authorized! Run telegram_login.py first.")
        return

    me = await client.get_me()
    print(f"Logged in as: {me.first_name} (@{me.username})\n")

    print("=" * 80)
    print("ALL CHANNELS & GROUPS")
    print("=" * 80)

    channels = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, Channel):
            username = f"@{entity.username}" if entity.username else f"ID:{entity.id}"
            ch_type = "channel" if entity.broadcast else "group"
            members = getattr(entity, 'participants_count', '?')
            channels.append({
                "title": dialog.title,
                "username": username,
                "id": entity.id,
                "type": ch_type,
                "broadcast": entity.broadcast,
            })

    # Sort: channels first, then groups
    channels.sort(key=lambda x: (0 if x["broadcast"] else 1, x["title"].lower()))

    print(f"\nFound {len(channels)} channels/groups:\n")

    for i, ch in enumerate(channels, 1):
        marker = "CH" if ch["broadcast"] else "GP"
        print(f"  {i:3}. [{marker}] {ch['title'][:40]:<40} {ch['username']:<25} (ID: {ch['id']})")

    await client.disconnect()

asyncio.run(main())
