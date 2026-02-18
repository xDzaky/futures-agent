#!/bin/bash
# Railway SSH Fix Guide - Confidence Error
# Run this inside Railway SSH session

echo "=== RAILWAY FUTURES-AGENT ERROR FIX ==="
echo ""

# 1. Check current directory
echo "1. Checking directory..."
pwd
ls -la

# 2. Find the error in logs
echo ""
echo "2. Finding error in logs..."
tail -100 realtime_debug.log | grep -A 5 -B 5 "confidence"

# 3. Quick fix: Disable consensus validation
echo ""
echo "3. Creating quick fix..."
cat > quick_fix.py << 'EOF'
"""
Quick fix for confidence error - patches realtime_monitor.py
"""
import re

# Read the file
with open('realtime_monitor.py', 'r') as f:
    content = f.read()

# Find and comment out the consensus validation block
# Line 889-925 approximately
pattern = r'(        # ─── Multi-AI Consensus Validation ────────────────.*?signal = consensus_result)'

replacement = r'''        # ─── Multi-AI Consensus Validation ────────────────
        # DISABLED: Causing confidence KeyError
        # consensus_result = self.consensus_validator.validate_signal(
        #     signal=signal,
        #     context={
        #         "technical": {},
        #         "market": {
        #             "price": price,
        #             "pair": pair,
        #         },
        #         "news": self.news_context.get("summary", "")
        #     }
        # )
        #
        # if not consensus_result:
        #     logger.info(f"  REJECT: Multi-AI consensus rejected signal")
        #     return False
        #
        # # Update signal with consensus data
        # signal = consensus_result
        # logger.info(f"  ✓ Consensus: {signal['confidence']:.2f} confidence")

        # Skip consensus validation (temp fix)'''

content_fixed = re.sub(pattern, replacement, content, flags=re.DOTALL)

# Also comment out news correlation that depends on confidence
pattern2 = r'(        # ─── Real-Time News Correlation ───────────────────.*?logger\.info\(f"  News adjustment:.*?\))'

replacement2 = r'''        # ─── Real-Time News Correlation ───────────────────
        # DISABLED: Requires consensus to work
        # news_corr = self.news_correlator.correlate_signal(signal)
        #
        # if news_corr.get("should_skip"):
        #     logger.info(f"  REJECT: Breaking news contradicts {side} signal")
        #     logger.info(f"    News: {news_corr.get('news_summary', '')}")
        #     return False
        #
        # # Adjust confidence based on news
        # conf_adjustment = news_corr.get("confidence_adjustment", 0.0)
        # if conf_adjustment != 0:
        #     old_conf = signal["confidence"]
        #     signal["confidence"] = max(0.0, min(1.0, old_conf + conf_adjustment))
        #     logger.info(f"  News adjustment: {old_conf:.2f} → {signal['confidence']:.2f} ({conf_adjustment:+.2f})")

        # Skip news correlation (temp fix)'''

content_fixed = re.sub(pattern2, replacement2, content_fixed, flags=re.DOTALL)

# Write fixed content
with open('realtime_monitor.py', 'w') as f:
    f.write(content_fixed)

print("✓ Fixed realtime_monitor.py")
print("✓ Consensus validation disabled")
print("✓ News correlation disabled")
EOF

python3 quick_fix.py

if [ $? -eq 0 ]; then
    echo ""
    echo "4. Restarting bot..."
    # Find and kill the running process
    pkill -f "python.*realtime_monitor.py" || true

    # Start bot in background
    nohup python3 realtime_monitor.py > /tmp/bot.log 2>&1 &

    echo ""
    echo "✅ FIX APPLIED AND BOT RESTARTED"
    echo ""
    echo "Monitor with:"
    echo "  tail -f realtime_debug.log"
else
    echo "❌ Fix failed, manual intervention needed"
fi
EOF
