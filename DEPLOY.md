# 🚀 Railway Deployment Guide

## ✅ STATUS: READY FOR DEPLOYMENT

Repository ini mengandung **Futures Trading Bot** dengan fitur:
- ✅ 52+ Telegram channel monitoring
- ✅ Manual signals via `/signal`
- ✅ **NEW**: Limit orders dengan auto-execution
- ✅ **NEW**: AI auto-research setiap 5 menit
- ✅ **NEW**: Trending coins detection
- ✅ **NEW**: Enhanced news (6 sources)

---

## 📋 ENVIRONMENT VARIABLES

Set variables ini di **Railway Dashboard** → Project Anda → Tab "Variables":

### **Telegram (Required)**
```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
TELEGRAM_API_ID=your_api_id_here
TELEGRAM_API_HASH=your_api_hash_here
TELEGRAM_PHONE=your_phone_here
```

### **AI Models (Required)**
```bash
GROQ_API_KEY=your_groq_key_here
NVIDIA_API_KEY=your_nvidia_key_here
TAVILY_API_KEY=your_tavily_key_here
```

### **Trading Config (Optional)**
```bash
STARTING_BALANCE=50.0
MAX_LEVERAGE=10
MAX_OPEN_POSITIONS=3
SCAN_INTERVAL_SECONDS=30
TRADING_PAIRS=BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT
USE_TESTNET=true
```

### **Feature Flags (Optional)**
```bash
ENABLE_AI_RESEARCH=true
RESEARCH_INTERVAL_MINUTES=5
MAX_RESEARCH_SEARCHES_PER_DAY=50
ENABLE_AI_CONSENSUS=true
ENABLE_NEWS_CORRELATION=true
MAX_ENTRY_DEVIATION=5.0
```

---

## 🚀 DEPLOY STEPS

### **1. Deploy dari GitHub**

1. Buka https://railway.app
2. Login dengan GitHub
3. **New Project** → **Deploy from GitHub repo**
4. Pilih: `xDzaky/futures-agent`
5. Click **Deploy**

### **2. Set Environment Variables**

Di Railway Dashboard → Project Anda → Tab **"Variables"**:

Copy-paste semua variables dari section di atas (ganti dengan values Anda).

**⚠️ PENTING:** Jangan commit `.env` ke Git! Set HANYA di Railway Dashboard.

### **3. Monitor Deployment**

Di Railway Dashboard → Tab **"Deployments"** → Click deployment yang berjalan.

**Expected logs:**
```
🚀 Starting Futures Agent on Railway...
⏳ Preparing database...
📦 Checking dependencies...
🔍 Running syntax check...
✅ limit_orders table created
✅ Database ready
════════════════════════════════════════
  ✅ All checks passed!
  🤖 Starting Realtime Monitor...
════════════════════════════════════════

[realtime] INFO: Connected to Telegram
[realtime] INFO: Initialized 52 signal channels
[ai_research] INFO: Groq client initialized
[trending] INFO: Scanning for trending coins...
```

---

## 📱 TEST BOT

### **1. Test di Telegram**

Kirim ke bot Anda:
```
/start
```

**Expected response:**
```
🤖 Futures Trading Agent
Active and monitoring markets 24/7.
Use /help to see available commands.
```

### **2. Test Commands**

```
/balance     → Show current balance
/status      → Show trading status
/channels    → List monitored channels (should show 52)
/signal LONG BTC 69000 TP 71000 SL 68000 → Manual signal
/signal_limit LONG BTC 69000 TP 71000 SL 68000 → Limit order
/pending     → Show pending limit orders
/research    → Trigger AI research
/trending    → Show trending coins
```

---

## 📊 MONITORING

### **Railway Dashboard:**
- **Usage**: CPU, Memory, Network
- **Logs**: Real-time logs
- **Deployments**: History & rollback

### **Bot Commands:**
```
/balance     → Current balance & P&L
/positions   → Open positions
/stats       → Trading statistics
/pending     → Limit orders
/trending    → Trending coins
/research    → AI research status
```

---

## ⚠️ TROUBLESHOOTING

### **Bot tidak start?**
1. Check logs di Railway Dashboard
2. Pastikan semua environment variables set
3. Check error message spesifik

### **"ModuleNotFoundError"?**
- Railway akan auto-install dependencies
- Check logs untuk confirm installation

### **"Rate limit exceeded"?**
Adjust di Railway Variables:
```bash
RESEARCH_INTERVAL_MINUTES=10  # dari 5
MAX_RESEARCH_SEARCHES_PER_DAY=30  # dari 50
```

### **Database error?**
- Normal di Railway (ephemeral FS)
- Database akan di-recreate setiap restart

---

## 💰 RAILWAY COST

**Free Tier:**
- $5 credit/month
- 500 hours runtime
- **Cukup untuk 24/7 bot**

**Estimated:**
```
CPU: 10-20% idle, 50-80% scanning
Memory: 200-400 MB
Network: Low (API calls)

Monthly: ~$0-5 (within free tier) ✅
```

---

## 🔄 UPDATE DEPLOYMENT

Railway akan **auto-deploy** setiap push ke GitHub:

```bash
# Edit code lokal
git add .
git commit -m "Update feature"
git push origin main

# Railway auto-deploy dalam ~1 menit
```

---

## 🔒 SECURITY

**✅ Aman:**
- API keys HANYA di Railway Dashboard
- `.env` di-ignore oleh `.gitignore`
- Dokumentasi menggunakan placeholders

**❌ Jangan:**
- Commit `.env` ke Git
- Hardcode API keys di code
- Share API keys di documentation

---

## 📁 FILES IN THIS REPO

**Core:**
- `realtime_monitor.py` — Main bot
- `run_aggressive.py` — Aggressive mode
- `ai_research_agent.py` — AI research
- `trending_tracker.py` — Trending detection
- `news_feeds.py` — News aggregation
- `trade_db.py` — Database

**Config:**
- `requirements.txt` — Dependencies
- `nixpacks.toml` — Railway config
- `start_railway.sh` — Startup script
- `.railwayignore` — Files to ignore

---

**Happy Trading! 🚀💰**
