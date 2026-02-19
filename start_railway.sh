#!/bin/bash
# Railway Startup Script
# Handles dependencies check, database migration, and bot startup

set -e

echo "🚀 Starting Futures Agent on Railway..."

# Wait for PostgreSQL (if using) or prepare SQLite
echo "⏳ Preparing database..."

# Create necessary directories
mkdir -p chart_images
mkdir -p logs

# Install additional dependencies if needed
echo "📦 Checking dependencies..."
pip install --quiet --no-cache-dir feedparser tavily-python 2>/dev/null || true

# Run syntax check on critical files
echo "🔍 Running syntax check..."
python3 -m py_compile realtime_monitor.py ai_analyzer.py news_feeds.py news_correlator.py 2>&1 || {
    echo "❌ Syntax error detected!"
    exit 1
}

# Check if .env variables are set
echo "🔐 Checking environment variables..."
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "⚠️  WARNING: TELEGRAM_BOT_TOKEN not set"
fi

if [ -z "$GROQ_API_KEY" ]; then
    echo "⚠️  WARNING: GROQ_API_KEY not set"
fi

# Clean up old database locks (Railway-specific)
echo "🧹 Cleaning up..."
rm -f *.db-shm *.db-wal 2>/dev/null || true

# Initialize database tables
echo "📊 Initializing database..."
python3 << 'EOF'
import sqlite3
import os

db_file = "futures_trades.db"
conn = sqlite3.connect(db_file)
cursor = conn.cursor()

# Check if limit_orders table exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='limit_orders'")
if not cursor.fetchone():
    print("Creating limit_orders table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS limit_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            trigger_condition TEXT DEFAULT 'LTE',
            quantity REAL,
            leverage INTEGER DEFAULT 1,
            margin REAL,
            position_value REAL,
            stop_loss REAL,
            tp1 REAL,
            tp2 REAL,
            tp3 REAL,
            sl_pct REAL,
            confidence REAL,
            source TEXT,
            signal_data TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at TEXT,
            triggered_at TEXT,
            triggered_price REAL,
            expire_at TEXT,
            cycle INTEGER DEFAULT 0
        )
    """)
    print("✅ limit_orders table created")
else:
    print("✅ limit_orders table exists")

conn.close()
print("✅ Database ready")
EOF

# Final check
echo ""
echo "════════════════════════════════════════"
echo "  ✅ All checks passed!"
echo "  🤖 Starting Realtime Monitor..."
echo "════════════════════════════════════════"
echo ""

# Start the bot
exec /opt/venv/bin/python realtime_monitor.py --balance 50
