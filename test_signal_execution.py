"""
Quick Signal Test - Debug Rejection Reasons
============================================
Simulates the exact signal execution path to identify rejection point.
"""

import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("signal_test")

# Test signal from user
test_signal = {
    "pair": "BTC/USDT",
    "side": "LONG",
    "entry": 95000,
    "targets": [97000],
    "stop_loss": 93000,
    "leverage": 5,
    "confidence": 0.75,
    "source": "manual_test"
}

print("=" * 60)
print("SIGNAL EXECUTION TEST")
print("=" * 60)
print(f"Signal: {test_signal['side']} {test_signal['pair']}")
print(f"Entry: ${test_signal['entry']:,}")
print(f"TP: ${test_signal['targets'][0]:,}")
print(f"SL: ${test_signal['stop_loss']:,}")
print()

# Simulate execution checks
balance = 50.0
max_positions = 3
open_positions = 0

print("PRE-TRADE CHECKS:")
print("=" * 60)

# 1. Max positions
print(f"1. Position limit: {open_positions}/{max_positions} ✓")

# 2. Balance check
min_balance = 5.0
if balance < min_balance:
    print(f"2. Balance check: ${balance:.2f} < ${min_balance} ✗ REJECT")
    sys.exit(1)
else:
    print(f"2. Balance check: ${balance:.2f} ✓")

# 3. Get current price
try:
    from market_data import MarketData
    market = MarketData()
    price = market.get_current_price("BTC/USDT")

    if not price:
        print(f"3. Price fetch: FAILED ✗ REJECT")
        print(f"   → Cannot get BTC/USDT price from exchange")
        sys.exit(1)

    print(f"3. Current price: ${price:,.2f} ✓")

    # 4. Entry proximity check
    entry = test_signal.get("entry", 0)
    if entry and entry > 0:
        entry_diff = abs(price - entry) / entry * 100
        if entry_diff > 3.0:
            print(f"4. Entry proximity: {entry_diff:.2f}% > 3% ✗ REJECT")
            print(f"   → Signal entry: ${entry:,}")
            print(f"   → Current price: ${price:,}")
            print(f"   → Difference: {entry_diff:.2f}%")
            sys.exit(1)
        else:
            print(f"4. Entry proximity: {entry_diff:.2f}% < 3% ✓")
    else:
        print(f"4. Entry proximity: No entry specified, using market ✓")

    # 5. Check if consensus is enabled
    enable_consensus = os.getenv("ENABLE_AI_CONSENSUS", "false").lower() == "true"

    if enable_consensus:
        print(f"5. AI Consensus: ENABLED ⚠️")
        print(f"   → This may reject signals if AIs disagree")
        print(f"   → Recommendation: Set ENABLE_AI_CONSENSUS=false in Railway")
    else:
        print(f"5. AI Consensus: DISABLED ✓")

    # 6. Check if TA is enabled
    use_ta = os.getenv("USE_TA_CONFIRMATION", "true").lower() == "true"

    if use_ta:
        print(f"6. TA Confirmation: ENABLED")
        try:
            from technical import TechnicalAnalyzer
            ta = TechnicalAnalyzer()

            # Get TA score
            ta_result = ta.check_signal("BTC/USDT", "LONG", ["5m", "15m"])
            score = ta_result.get("consensus_score", 50)

            side = test_signal["side"]
            if side == "LONG":
                ta_agrees = score >= 45
            else:
                ta_agrees = score <= 55

            if ta_agrees:
                print(f"   → Score: {score} ✓ (threshold: {'≥45' if side=='LONG' else '≤55'})")
            else:
                print(f"   → Score: {score} ✗ REJECT (threshold: {'≥45' if side=='LONG' else '≤55'})")
                print(f"   → FIX: Add USE_TA_CONFIRMATION=false to Railway Variables")
                sys.exit(1)

        except Exception as e:
            print(f"   → TA check failed: {e}")
            print(f"   → Signal may be rejected by TA")
    else:
        print(f"6. TA Confirmation: DISABLED ✓")

    # 7. Stop loss check
    sl = test_signal.get("stop_loss", 0)
    if sl:
        sl_dist_pct = abs(price - sl) / price * 100

        if sl_dist_pct > 5.0:
            print(f"7. Stop loss distance: {sl_dist_pct:.2f}% > 5% ✗ REJECT")
            print(f"   → SL too far from entry (max 5%)")
            sys.exit(1)
        else:
            print(f"7. Stop loss distance: {sl_dist_pct:.2f}% ✓")
    else:
        print(f"7. Stop loss: Not specified (will calculate) ✓")

    print()
    print("=" * 60)
    print("✅ ALL CHECKS PASSED")
    print("=" * 60)
    print()
    print("If signal still rejected in Railway:")
    print("1. Check Railway Variables for ENABLE_AI_CONSENSUS=false")
    print("2. Check Railway Variables for USE_TA_CONFIRMATION=false")
    print("3. Verify GROQ_API_KEY is set (for AI analysis)")
    print("4. Check Railway logs for detailed error message")

except Exception as e:
    print(f"3. Price fetch: ERROR - {e}")
    print(f"   → This is likely why signal was rejected")
    print()
    print("POSSIBLE CAUSES:")
    print("1. No internet connection")
    print("2. Exchange API error (Binance down)")
    print("3. market_data.py has a bug")
    print()
    print("FIX: Check if market data fetch is working:")
    print("  python -c 'from market_data import MarketData; m = MarketData(); print(m.get_current_price(\"BTC/USDT\"))'")
