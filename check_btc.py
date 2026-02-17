
import sys
import os
from market_data import MarketData
from trade_db import TradeDB

# Initialize Market Data
print("Initializing Market Data...")
md = MarketData()

# Check BTC Price
symbol = "BTC/USDT"
print(f"Fetching current price for {symbol}...")
price = md.get_current_price(symbol)

if price:
    print(f"✅ SUCCESS: Current {symbol} price is ${price:,.2f}")
else:
    print(f"❌ ERROR: Could not fetch price for {symbol}")

# Verify Balance from DB
print("\nVerifying Balance...")
try:
    db = TradeDB("realtime_trades.db", 50.0)
    stats = db.get_stats()
    balance = stats.get("balance")
    print(f"Current Balance: ${balance:,.2f}")
    
    if abs(balance - 50.0) < 0.01 and stats.get("total_trades") == 0:
        print("✅ SUCCESS: Balance is correctly set to $50.00 (Demo Mode)")
    elif balance > 0:
         print(f"✅ SUCCESS: Balance exists (${balance:,.2f})")
    else:
        print("❌ ERROR: Balance is 0 or invalid")
        
except Exception as e:
    print(f"❌ ERROR reading DB: {e}")

print("\n--- Futures Agent Sensitivity Check ---")
print("Agent is designed to TRADE futures (Long/Short).")
print("Different from Polymarket (Prediction Markets).")
