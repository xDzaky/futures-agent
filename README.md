# Crypto Futures Real-Time Signal Monitor

Automated crypto futures trading system with real-time Telegram signal monitoring, AI analysis, and paper trading.

## Features

- **Real-time signal monitoring** from 14 Telegram channels (no polling, event-driven)
- **AI-powered analysis** (Groq Llama 3.3 70B + Google Gemini Vision)
- **Multi-source signals**: Structured signals (parse entry/TP/SL) + AI-analyzed text/images
- **Technical analysis confirmation** before entry
- **News sentiment** analysis for market context
- **Trailing stops** with TP-based SL adjustment
- **Anti-liquidation safeguards** (max positions, drawdown limits, loss streak protection)
- **Telegram bot commands** (/balance, /status, /positions, /stats, /signal)

## 📊 Monitored Channels

**Tier 1 - Structured Signals** (direct parsing):
- Binance 360 (110K members)
- Crypto Bulls (87K)
- Rose Paid Crypto Free (175K)
- Crypto World Updates (183K)

**Tier 2 - Analysis** (AI interprets):
- Wyann's Crypto Journal (12K, Indonesian + charts)
- Rose Premium Signals (177K)
- KJo Academy (30K)
- Evolution Trading (9K)
- Crypto Teknikal (33K)

**Tier 3 - News** (sentiment context):
- Cointelegraph (392K)
- Sailly's Trading Group (49K)
- Ash Crypto (66K)
- SM News (34K)
- CRYPTO NEWS (58K)

## 🚀 Railway Deployment

### 1. Create Railway Project

1. Go to [railway.app](https://railway.app)
2. Click "New Project" → "Deploy from GitHub repo"
3. Connect your GitHub account
4. Select `ai-agents/futures-agent` repository

### 2. Set Environment Variables

In Railway dashboard → Variables, add these:

```bash
# Telegram Bot (for notifications and commands)
TELEGRAM_BOT_TOKEN=your_bot_token_from_@BotFather
TELEGRAM_CHAT_ID=your_telegram_user_id

# Telegram User API (for reading channels)
TELEGRAM_API_ID=your_api_id_from_my.telegram.org
TELEGRAM_API_HASH=your_api_hash_from_my.telegram.org
TELEGRAM_PHONE=+62xxxxxxxxxx

# Groq AI (FREE - get from console.groq.com)
GROQ_API_KEY=gsk_xxxxx

# Gemini Vision (OPTIONAL - get from ai.google.dev)
GEMINI_API_KEY=AIzaSyxxxxx

# Trading pairs (comma-separated, no spaces)
TRADING_PAIRS=BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT

# Signal channels (comma-separated, @username format)
SIGNAL_CHANNELS=@binance_360,@MWcryptojournal
```

### 3. Deploy

Railway will automatically:
- Detect `Procfile`
- Install dependencies from `requirements.txt`
- Run `realtime_monitor.py`

### 4. View Logs

Railway dashboard → Deployments → View logs

Monitor will start and show:
```
REAL-TIME SIGNAL MONITOR STARTING
Logged in as: YourName
+ Monitoring 14 channels
Bot command polling started
Waiting for signals...
```

### 5. Test Bot Commands

Send to your Telegram bot:
- `/help` - Show all commands
- `/balance` - Show balance
- `/status` - Trading status
- `/positions` - Open positions
- `/stats` - Full statistics
- `/channels` - List monitored channels
- `/signal LONG BTC 69000 TP 71000 SL 68000` - Manual signal

## 📱 Telegram Notifications

Bot automatically sends notifications for:

**Trade Opened:**
```
📊 TRADE OPENED
LONG BTC/USDT @ $69,234.50
Leverage: 15x
SL: $67,890.12 (1.94%)
TP1: $71,500.00
Margin: $12.50
Source: ai:Binance_360
```

**Trade Closed:**
```
✅ WIN TRADE CLOSED
LONG BTC/USDT @ $71,500.00
Reason: TP1
P&L: $+3.75 (+7.5%)
Balance: $53.75
```

## 🔒 Anti-Liquidation Features

- **Max 3 positions** at once
- **Max 30% drawdown** → pause trading
- **4 consecutive losses** → cooldown
- **Max 5% SL distance** per trade
- **Emergency close** at -20% leveraged loss
- **Trailing stops**: TP1 → SL to entry, TP2 → SL to breakeven+

## 🧪 Testing (1 Week Demo)

Monitor runs with:
- Starting balance: **$50**
- Max leverage: **20x**
- Risk per trade: **10%**
- Max positions: **3**
- TA confirmation: **ON**

**Expected results after 1 week:**
- Total trades: 15-30 (depends on signal frequency)
- Win rate: 45-65% (aggressive mode)
- Target ROI: 50-150% (high risk)

Track progress with `/stats` command daily.

## 📊 Architecture

```
Telegram Channels (14)
    ↓
Event Handler (Telethon)
    ↓
┌─────────────────┬──────────────────┬─────────────────┐
│  Tier 1         │  Tier 2          │  Tier 3         │
│  Parse Direct   │  AI Analysis     │  News Context   │
│  entry/TP/SL    │  Groq + Gemini   │  Sentiment      │
└─────────────────┴──────────────────┴─────────────────┘
    ↓
TA Confirmation (4 timeframes)
    ↓
Risk Checks (positions, drawdown, SL)
    ↓
Execute Trade (paper trading)
    ↓
Monitor (SL/TP checks every 10s)
    ↓
Telegram Notification
```

## 🛠️ Local Development

```bash
cd /home/dzaky/Desktop/ai-agents/futures-agent

# Install dependencies
pip install -r requirements.txt

# Copy .env.example to .env and fill in credentials
cp .env.example .env

# Run monitor
python realtime_monitor.py --balance 50 --max-leverage 20

# Or start in background
nohup python realtime_monitor.py --balance 50 > output.log 2>&1 &

# Check status
python realtime_monitor.py --status

# List monitored channels
python realtime_monitor.py --list-channels

# Reset (start fresh)
python realtime_monitor.py --reset --balance 50
```

## ⚠️ Disclaimer

**THIS IS PAPER TRADING FOR TESTING ONLY.**

- No real money involved
- No exchange connection
- Simulated P&L only
- For educational purposes

**If you want to connect to real exchange:**
1. Uncomment exchange config in `market_data.py`
2. Add `EXCHANGE_API_KEY` and `EXCHANGE_API_SECRET` to env
3. Change `paper_trading=True` to `False` in code
4. **START WITH SMALL AMOUNTS**

## 📈 Performance Tracking

Monitor your 1-week test:

| Metric | Value |
|--------|-------|
| Starting Balance | $50.00 |
| Current Balance | Check `/balance` |
| Total Trades | Check `/stats` |
| Win Rate | Check `/stats` |
| ROI | Check `/balance` |
| Signals Processed | Check `/stats` |

Good luck! 🚀
