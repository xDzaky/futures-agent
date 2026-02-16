# 🚀 Quick Start - Railway Deployment

## 1. Prerequisites

- GitHub account
- Railway account (free: railway.app)
- Telegram Bot Token (from @BotFather)
- Telegram API credentials (from my.telegram.org)
- Groq API key (free from console.groq.com)

## 2. Push to GitHub

```bash
cd /home/dzaky/Desktop/ai-agents/futures-agent

git init
git add .
git commit -m "Initial commit - Crypto Futures AI Agent"
git remote add origin https://github.com/YOUR_USERNAME/futures-agent.git
git branch -M main
git push -u origin main
```

## 3. Deploy to Railway

1. Go to **railway.app** → Login
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose your `futures-agent` repository
5. Railway will auto detect `Procfile` and start deployment

## 4. Configure Environment Variables

In Railway dashboard → **Variables** tab, add:

```
TELEGRAM_BOT_TOKEN=7123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
TELEGRAM_CHAT_ID=6167580651
TELEGRAM_API_ID=37423616
TELEGRAM_API_HASH=7d5b2c0c4c33e02ffd468bf3fc9b9f69
TELEGRAM_PHONE=+6281216494184
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxx
GEMINI_API_KEY=AIzaSyxxxxxxxxxxxxxx (optional)
TRADING_PAIRS=BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT
SIGNAL_CHANNELS=@binance_360,@MWcryptojournal
```

> **⚠️ Important**: Copy values from your `.env` file!

## 5. Verify Deployment

Check Railway logs, you should see:

```
REAL-TIME SIGNAL MONITOR STARTING
============================================================
Logged in as: Dzaky (@DzakyAr)
  + 1:signal   Binance 360
  + 1:signal   Crypto Bulls®
  ...
  + 3:news     CRYPTO NEWS
Bot command polling started (BOT_TOKEN configured)
Monitoring 14 channels in real-time
Balance: $50.00 | Max leverage: 20x
TA confirmation: ON
Anti-liquidation: max 3 positions, 30% max drawdown
Waiting for signals...
============================================================
```

## 6. Test Commands

Open Telegram and send to your bot:

```
/help
```

You should get:

```
Available Commands:

/balance - Show current balance
/status - Show trading status
/positions - Show open positions
/stats - Show statistics
/signal LONG BTC 69000 TP 71000 SL 68000 - Manual signal
/channels - List monitored channels
/help - Show this help
```

## 7. Monitor Performance

**Daily checks (recommended):**

Morning:
```
/status   → Check overnight performance
/positions → Any open trades?
```

Evening:
```
/stats    → See full statistics
/balance  → Check ROI
```

**Expected notifications:**

When signal is detected:
```
📊 TRADE OPENED
LONG BTC/USDT @ $69,234.50
Leverage: 15x
SL: $67,890.12 (1.94%)
TP1: $71,500.00
Margin: $12.50
Source: ai:Binance_360
```

When TP/SL hits:
```
✅ WIN TRADE CLOSED
LONG BTC/USDT @ $71,500.00
Reason: TP1
P&L: $+3.75 (+7.5%)
Balance: $53.75
```

## 8. Troubleshooting

**Bot not responding?**
- Check Railway logs for errors
- Verify `TELEGRAM_BOT_TOKEN` is correct
- Verify `TELEGRAM_CHAT_ID` matches your user ID

**No signals detected?**
- Check Railway logs: "Bot command polling started"
- Wait 10-30 minutes (channels post irregularly)
- Send `/channels` to verify 14 channels are monitored

**Telegram login failed?**
- Verify `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_PHONE`
- If 2FA enabled: disable it temporarily or add 2FA password handling
- Check Railway logs for "Logged in as: YourName"

## 9. Stop/Restart

**Restart deployment:**
Railway dashboard → Deployments → Click "Restart"

**Stop:**
Railway dashboard → Settings → "Remove Service"

## 10. Track 1-Week Progress

Create a spreadsheet to track daily:

| Day | Balance | ROI | Trades | Win Rate | Open Positions |
|-----|---------|-----|--------|----------|----------------|
| Mon | $50.00  | 0%  | 0      | -        | 0              |
| Tue | $52.30  | +4.6% | 3    | 66.7%    | 1              |
| ...

Use `/stats` command daily at same time.

**Target after 1 week:**
- Balance: $75-125 (50-150% ROI in aggressive mode)
- Win Rate: 45-65%
- Total Trades: 15-30

Good luck! 🚀

---

## Need Help?

Check Railway logs:
```
Railway dashboard → Deployments → View logs
```

Check bot status locally:
```bash
python realtime_monitor.py --status
```

View all files:
```bash
ls -la
```
