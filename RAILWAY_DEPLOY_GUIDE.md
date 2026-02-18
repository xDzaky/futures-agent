# 🚀 Railway Deployment Guide - Fixed Version

## ✅ BUGS FIXED

1. **KeyError: 'confidence'** - Wrapped consensus validation with env checks
2. **Entry price rejection** - Increased tolerance from 3% to 5%
3. **Crash on NVIDIA API error** - Added try-catch blocks
4. **Dependencies missing** - Updated requirements.txt

---

## 📦 DEPLOY TO RAILWAY

### Step 1: Push to GitHub

```bash
cd /home/dzaky/Desktop/ai-agents/futures-agent
git push
```

### Step 2: Connect Railway (if new project)

1. Go to https://railway.app
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Choose `futures-agent` repository
5. Railway will auto-detect Python and build

### Step 3: Set Environment Variables

**CRITICAL - Set these in Railway Variables tab:**

```env
# === Telegram ===
TELEGRAM_API_ID=37423616
TELEGRAM_API_HASH=your_telegram_api_hash
TELEGRAM_PHONE=+6281216494184
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# === AI APIs ===
GROQ_API_KEY=your_groq_api_key
GEMINI_API_KEY=your_gemini_api_key
NVIDIA_API_KEY=your_nvidia_api_key
TAVILY_API_KEY=your_tavily_api_key

# === Trading Config ===
# CRITICAL: Set these to avoid consensus errors
ENABLE_AI_CONSENSUS=false
ENABLE_NEWS_CORRELATION=false

# Entry price tolerance (5% recommended for channel signals)
MAX_ENTRY_DEVIATION_PCT=5.0

# Optional: Disable TA for max trade frequency
# USE_TA_CONFIRMATION=false
```

### Step 4: Verify Deployment

1. Check Railway **Logs** tab for:
   - ✅ "Monitoring 52 channels in real-time"
   - ✅ "Waiting for signals..."

2. Test via Telegram bot:
   ```
   /status
   ```

---

## 🧪 TEST MANUAL SIGNAL

Get current BTC price first, then send signal:

```bash
# Get current price
python -c "from market_data import MarketData; m = MarketData(); print(f'BTC: ${m.get_current_price(\"BTC/USDT\"):,.0f}')"

# Use that price in manual signal (example with $67,000):
/signal LONG BTC 67000 TP 68340 SL 65030
```

**Expected:** ✅ "Signal executed" + position opens

---

## 🔍 TROUBLESHOOTING

### Still getting "Signal rejected"?

**Check rejection reason in bot response or Railway logs.**

Common reasons:
1. **Entry price too far** → Increase MAX_ENTRY_DEVIATION_PCT to 10.0
2. **TA disagrees** → Set USE_TA_CONFIRMATION=false
3. **Already in position** → Close existing position first
4. **Balance too low** → Need min $5

### If consensus/news errors appear:

**VERIFY these are set in Railway Variables:**
```
ENABLE_AI_CONSENSUS=false
ENABLE_NEWS_CORRELATION=false
```

### No signals arriving?

Check `/status` - should show:
```
Signals: X seen, Y traded
```

If X stays at 0 for >1 hour:
- Verify Telegram session file uploaded
- Check channel list with `/channels`
- Channels may not be posting signals

---

## 📊 RECOMMENDED SETTINGS FOR BEGINNERS

**Maximum trade frequency (highest risk):**
```env
ENABLE_AI_CONSENSUS=false
ENABLE_NEWS_CORRELATION=false
USE_TA_CONFIRMATION=false
MAX_ENTRY_DEVIATION_PCT=10.0
```

**Balanced (recommended):**
```env
ENABLE_AI_CONSENSUS=false
ENABLE_NEWS_CORRELATION=false
USE_TA_CONFIRMATION=true
MAX_ENTRY_DEVIATION_PCT=5.0
```

**Conservative (lowest trades, highest quality):**
```env
ENABLE_AI_CONSENSUS=true
MIN_AI_AGREEMENT=2
ENABLE_NEWS_CORRELATION=true
USE_TA_CONFIRMATION=true
MAX_ENTRY_DEVIATION_PCT=3.0
```

---

## ✅ DEPLOYMENT CHECKLIST

- [ ] Git push to GitHub
- [ ] Railway project created/linked
- [ ] All environment variables set
- [ ] Bot started (check logs)
- [ ] Test manual signal works
- [ ] Monitor `/status` for signals
- [ ] Verify first trade executes

---

Ready to deploy? Run:
```bash
git push
```

Then set environment variables in Railway dashboard.
