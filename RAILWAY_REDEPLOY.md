# 🔧 RAILWAY RE-DEPLOY INSTRUCTIONS

## ✅ FIXES DEPLOYED

**Commit:** `f87d157` - "fix: Add missing commands and fix Groq rate limit"

**Changes:**
- ✅ Added `/pending`, `/trending`, `/signal_limit`, `/cancel_limit`, `/research` commands
- ✅ Fixed Groq rate limit (429) with exponential backoff
- ✅ Added fallback to keyword analysis when Groq unavailable
- ✅ Updated `/help` with all commands

---

## 🚀 FORCE RAILWAY RE-DEPLOY

Railway **should auto-deploy** when you push to GitHub, but if it doesn't:

### **Method 1: Via Railway Dashboard (Recommended)**

1. Buka https://railway.app
2. Login → Pilih project `futures-agent`
3. Tab **"Deployments"**
4. Click **"Deploy"** button (atau "Redeploy")
5. Wait ~1-2 menit untuk deployment

### **Method 2: Trigger via Git**

```bash
cd /home/dzaky/Desktop/ai-agents/futures-agent
git commit --allow-empty -m "chore: Trigger Railway re-deploy"
git push origin main
```

Railway akan detect push baru dan auto-deploy.

---

## ✅ VERIFY DEPLOYMENT

### **1. Check Railway Logs**

Di Railway Dashboard → Project Anda → Tab **"Deployments"**:

**Expected:**
```
✅ Deployment started
✅ Building...
✅ Deploying...
✅ Success
```

### **2. Check Bot Commands**

Setelah deployment sukses, test di Telegram:

```
/help
```

**Expected response:**
```
Available Commands:

/balance - Show current balance
/status - Show trading status
/positions - Show open positions
/stats - Show statistics
/signal LONG BTC 69000 TP 71000 SL 68000 - Manual signal
/signal_limit LONG BTC 69000 TP 71000 SL 68000 - Limit order
/pending - View pending limit orders
/cancel_limit 123 - Cancel limit order
/trending - View trending coins
/research [COIN] - Trigger AI research
/channels - List monitored channels
/help - Show this help
```

### **3. Test New Commands**

```
/pending
```
**Expected:** "📋 No pending limit orders" (atau list orders jika ada)

```
/trending
```
**Expected:** List trending coins dengan score

```
/signal_limit LONG BTC 69000 TP 71000 SL 68000
```
**Expected:** "📌 Limit order created #X"

---

## ⚠️ TROUBLESHOOTING

### **Railway tidak auto-deploy?**

**Solution:**
1. Buka Railway Dashboard
2. Project Anda → Tab "Settings"
3. Scroll ke bawah
4. Click "Deploy" → "Redeploy"

### **Commands masih "Unknown"?**

**Possible causes:**
1. Deployment belum selesai → Wait 1-2 menit
2. Bot belum restart → Check logs untuk "REAL-TIME MONITOR STARTED"
3. Cache issue → Restart bot di Railway (Settings → Restart)

### **Groq 429 error masih muncul?**

**Normal behavior:** Bot sekarang akan fallback ke keyword analysis saat rate limit.

**Check logs untuk:**
```
[WARNING] Groq rate limit hit - using keyword fallback
```

Ini **EXPECTED** dan bot akan tetap berfungsi dengan keyword analysis.

**Untuk reduce rate limit:**
Set di Railway Variables:
```bash
RESEARCH_INTERVAL_MINUTES=15  # dari 5
MAX_RESEARCH_SEARCHES_PER_DAY=20  # dari 50
```

---

## 📊 EXPECTED RESULTS

After re-deploy:

```
✅ All new commands working
✅ No more "Unknown command" errors
✅ Groq 429 errors handled gracefully
✅ Bot continues processing during rate limits
✅ Keyword fallback working
```

---

## 🎯 NEXT STEPS

1. ✅ Force re-deploy di Railway (Method 1 atau 2)
2. ✅ Wait deployment complete (~1-2 min)
3. ✅ Test `/help` command
4. ✅ Test `/pending`, `/trending`, `/signal_limit`
5. ✅ Monitor logs for any errors

---

**Good luck! Bot akan berfungsi penuh setelah re-deploy! 🚀**
