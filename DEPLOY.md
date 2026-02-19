# 🚀 Railway Deployment - Quick Guide

## ✅ STATUS: READY FOR DEPLOYMENT

Repository sudah bersih dari API keys dan siap untuk deploy.

---

## 📋 ENVIRONMENT VARIABLES

Set variables ini di Railway Dashboard:

```bash
# Telegram (Required)
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
TELEGRAM_API_ID=your_api_id_here
TELEGRAM_API_HASH=your_api_hash_here

# AI Models (Required)
GROQ_API_KEY=your_groq_key_here
NVIDIA_API_KEY=your_nvidia_key_here
TAVILY_API_KEY=your_tavily_key_here

# Trading Config
STARTING_BALANCE=50.0
MAX_LEVERAGE=10
USE_TESTNET=true
```

**⚠️ PENTING:** Jangan commit API keys ke Git! Set hanya di Railway Dashboard.

---

## 🚀 DEPLOY STEPS

1. **Push ke GitHub** (sudah dilakukan ✅)
2. **Connect di Railway** → Pilih repo ini
3. **Set Environment Variables** di Railway Dashboard
4. **Deploy** - Railway akan auto-deploy

---

## 📁 FILES IN THIS REPO

✅ `realtime_monitor.py` - Main bot dengan Telegram integration
✅ `run_aggressive.py` - Aggressive trading mode dengan limit orders
✅ `requirements.txt` - Python dependencies
✅ `nixpacks.toml` - Railway build configuration

---

## 🧪 TEST AFTER DEPLOY

Check logs di Railway Dashboard:
```
✅ "Starting Futures Agent..."
✅ "Connected to Telegram"
✅ "Initialized signal channels"
```

Test Telegram Bot:
```
/start → Bot should respond
```

---

**Happy Trading! 🚀**
