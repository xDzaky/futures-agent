# 🚀 Railway Deployment Guide - Futures Agent

## ✅ Status: READY FOR DEPLOYMENT

Project sudah dikonfigurasi dengan benar untuk deployment ke Railway.

---

## 📋 File Konfigurasi yang Sudah Diperbaiki

| File | Status | Keterangan |
|------|--------|------------|
| `package.json` | ✅ Created | Required by Railway for Nixpacks |
| `nixpacks.toml` | ✅ Created | Python 3.11 build config |
| `railway.json` | ✅ Updated | Deployment policy & healthcheck |
| `Procfile` | ✅ Exists | Worker entry point |
| `runtime.txt` | ✅ Exists | Python version |
| `requirements.txt` | ✅ Exists | All dependencies |
| `.railwayignore` | ✅ Updated | Clean ignore list |
| `.gitignore` | ✅ Updated | Secure ignore list |
| `.env.example` | ✅ Updated | Template env vars |

---

## 🔑 Environment Variables yang Diperlukan

**IMPORTANT:** Jangan commit `.env` ke GitHub! Set variables ini di Railway Dashboard:

### Required (WAJIB):
```bash
# Telegram Bot (for commands & notifications)
TELEGRAM_BOT_TOKEN=7943253616:AAHf30ALGf3eSOJtzFAZE35Dq2v5ZKSu2-o
TELEGRAM_CHAT_ID=6167580651

# Telegram User API (for reading signal channels)
TELEGRAM_API_ID=your_telegram_api_id
TELEGRAM_API_HASH=your_telegram_api_hash
TELEGRAM_PHONE=+6281216494184

# AI Models
GROQ_API_KEY=your_groq_api_key
NVIDIA_API_KEY=your_nvidia_api_key
TAVILY_API_KEY=your_tavily_api_key

# News APIs (optional but recommended)
NEWSAPI_KEY=your_newsapi_key
FINNHUB_API_KEY=your_finnhub_api_key
```

### Optional:
```bash
# Exchange API (only if using real trading)
BINANCE_TESTNET_KEY=
BINANCE_TESTNET_SECRET=

# Config overrides (defaults already set in code)
STARTING_BALANCE=50.0
TRADING_PAIRS=BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT
SIGNAL_CHANNELS=@MWcryptojournal,@binance_360
```

---

## 📦 Langkah Deployment

### Step 1: Push ke GitHub

```bash
cd /home/dzaky/Desktop/ai-agents/futures-agent

# Initialize git jika belum
git init
git add .
git commit -m "Prepare for Railway deployment"

# Buat repo baru di GitHub, lalu:
git remote add origin https://github.com/YOUR_USERNAME/futures-agent.git
git branch -M main
git push -u origin main
```

### Step 2: Deploy di Railway

1. Buka https://railway.app
2. Login dengan GitHub
3. Klik **"New Project"**
4. Pilih **"Deploy from GitHub repo"**
5. Pilih repository `futures-agent`
6. Railway akan otomatis build

### Step 3: Set Environment Variables

Di Railway Dashboard:
1. Klik project kamu
2. Pilih tab **"Variables"**
3. Klik **"New Variable"**
4. Copy-paste semua env vars dari `.env` kamu

### Step 4: Monitor Deployment

1. Pilih tab **"Logs"** di Railway Dashboard
2. Tunggu build selesai (~2-5 menit)
3. Verify tidak ada error

---

## 🧪 Testing Setelah Deploy

### Test 1: Bot Commands
Kirim ke bot Telegram kamu:
```
/help
```
Expected: List commands

### Test 2: Check Balance
```
/balance
```
Expected:
```
💰 Balance
Balance: $50.00
Total P&L: $0.00
Starting: $50.00
```

### Test 3: Check Channels
```
/channels
```
Expected: List monitored channels

### Test 4: Wait for Signal
Tunggu 10-30 menit untuk signal trading pertama.

---

## ⚙️ Configuration Details

### Start Command
```bash
python realtime_monitor.py --balance 50
```

### Build Process (Nixpacks)
```toml
[phases.setup]
nixPkgs = ["python311"]

[phases.install]
cmds = ["pip install --no-cache-dir -r requirements.txt"]
```

### Restart Policy
- Type: `ON_FAILURE`
- Max Retries: `10`
- Healthcheck Timeout: `300s`

---

## 📊 Expected Behavior

### Startup Logs
```
REAL-TIME SIGNAL MONITOR STARTING
============================================================
Logged in as: [Your Name]
  + 1:signal   Binance 360
  + 1:signal   Crypto Bulls
  ...
Bot command polling started
Monitoring 14 channels in real-time
Balance: $50.00 | Max leverage: 20x
Waiting for signals...
```

### When Signal Detected
```
📊 TRADE OPENED
LONG BTC/USDT @ $69,234.50
Leverage: 15x | Margin: $12.50
SL: $67,890.12
TP1: $71,500.00
Source: @binance_360
```

---

## ⚠️ Important Notes

### 1. Database is Ephemeral
Railway filesystem is temporary. Trade history stored in SQLite will be lost on restart. This is expected behavior.

### 2. Session Persistence
Telegram session (`*.session`) will be recreated on each restart. Normal behavior.

### 3. Image Analysis
- Uses NVIDIA NIM Vision (FREE)
- Replaces Gemini (key was leaked)
- Works same as Gemini but more reliable

### 4. Cost Estimate
- Railway Free: 500 hours/month (~20 days)
- For 24/7: Upgrade to Hobby ($5/month)
- All APIs used are FREE tier

---

## 🛑 Troubleshooting

### Build Failed
```
Error: No start command found
```
**Fix:** Ensure `package.json` and `Procfile` exist

### Bot Not Responding
```
No response to /help command
```
**Fix:** Check Railway logs, verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`

### No Signals Detected
```
No trades after 1+ hour
```
**Fix:** 
- Check `/channels` - verify channels are connected
- Wait longer - signals are irregular
- Check channel activity manually

### Image Analysis Failed
```
NVIDIA API error: 429
```
**Fix:** Rate limit - wait a few minutes, text analysis still works

---

## 📈 Performance Tracking

Use these commands daily:
```
/stats       # Full statistics
/balance     # Current balance
/positions   # Open trades
/history     # Trade history
```

### Target Metrics (1 Week)
- Starting: $50.00
- Target: $75-125 (50-150% ROI)
- Win Rate: 45-65%
- Total Trades: 15-30

---

## ✨ Checklist Before Deploy

- [ ] `.env` NOT committed to git
- [ ] All env vars ready to copy
- [ ] GitHub repo created (private recommended)
- [ ] Railway account created
- [ ] Telegram bot token from @BotFather
- [ ] Telegram API credentials from my.telegram.org
- [ ] GROQ API key from console.groq.com
- [ ] NVIDIA API key from build.nvidia.com

---

## 🔗 Useful Links

- Railway Docs: https://docs.railway.app
- Nixpacks: https://nixpacks.com
- Groq Console: https://console.groq.com
- NVIDIA NIM: https://build.nvidia.com
- Telegram API: https://my.telegram.org

---

**Status:** 🟢 READY TO DEPLOY
**Last Updated:** 2026-02-19
**Balance Config:** $50.00 (Testnet/Paper Trading)
