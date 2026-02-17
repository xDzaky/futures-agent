"""
Signal Flow Debugger
=====================
Simulates signal processing to identify where signals are being rejected.
"""

import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

# Test if consensus is enabled and too strict
enable_consensus = os.getenv("ENABLE_AI_CONSENSUS", "true").lower() == "true"
min_agreement = int(os.getenv("MIN_AI_AGREEMENT", "2"))
enable_news = os.getenv("ENABLE_NEWS_CORRELATION", "true").lower() == "true"

print("=" * 60)
print("SIGNAL FLOW DIAGNOSTICS")
print("=" * 60)
print(f"AI Consensus: {'ENABLED' if enable_consensus else 'DISABLED'}")
print(f"Min AI Agreement: {min_agreement}/3")
print(f"News Correlation: {'ENABLED' if enable_news else 'DISABLED'}")
print()

# Test signal
test_signal = {
    "pair": "BTC/USDT",
    "side": "LONG",
    "entry": 95000,
    "stop_loss": 93000,
    "targets": [97000, 99000],
    "leverage": 5,
    "confidence": 0.70,
    "source": "test"
}

print("Test Signal:")
for k, v in test_signal.items():
    print(f"  {k}: {v}")
print()

# Check API keys
print("API Keys Status:")
groq_key = os.getenv("GROQ_API_KEY", "")
nvidia_key = os.getenv("NVIDIA_API_KEY", "")
tavily_key = os.getenv("TAVILY_API_KEY", "")
gemini_key = os.getenv("GEMINI_API_KEY", "")

print(f"  GROQ: {'✓ Configured' if groq_key else '✗ MISSING'}")
print(f"  NVIDIA: {'✓ Configured' if nvidia_key else '✗ MISSING'}")
print(f"  Tavily: {'✓ Configured' if tavily_key else '✗ MISSING'}")
print(f"  Gemini: {'✓ Configured' if gemini_key else '✗ Configured'}")
print()

# Check if consensus will reject due to missing APIs
if enable_consensus:
    available_validators = 0
    if groq_key:
        available_validators += 1
    if nvidia_key:
        available_validators += 1

    print(f"Available AI Validators: {available_validators}")

    if available_validators < min_agreement:
        print(f"⚠️  WARNING: Only {available_validators} validators available, but need {min_agreement} for consensus!")
        print(f"   RECOMMENDATION: Set MIN_AI_AGREEMENT={available_validators} or disable consensus")
    else:
        print(f"✓ Consensus validation will work ({available_validators} >= {min_agreement})")
    print()

# Test consensus if enabled
if enable_consensus and (groq_key or nvidia_key):
    print("Testing Consensus Validator...")
    try:
        from consensus_validator import ConsensusValidator
        validator = ConsensusValidator()

        result = validator.validate_signal(
            signal=test_signal,
            context={
                "technical": {"consensus_score": 70, "signal": "LONG"},
                "market": {"price": 95000},
                "news": "Bitcoin showing strength"
            }
        )

        if result:
            print(f"  ✓ Signal APPROVED by consensus")
            print(f"    Final confidence: {result.get('confidence', 0):.2f}")
            if result.get('consensus'):
                cons = result['consensus']
                print(f"    Votes: {cons.get('votes_for', 0)}/{cons.get('total_votes', 0)} agreed")
        else:
            print(f"  ✗ Signal REJECTED by consensus")
            print(f"    This is why no trades are executing!")

    except Exception as e:
        print(f"  ✗ Consensus test failed: {e}")
    print()

# Test news correlation if enabled
if enable_news and tavily_key:
    print("Testing News Correlator...")
    try:
        from news_correlator import NewsCorrelator
        correlator = NewsCorrelator()

        result = correlator.correlate_signal(test_signal)

        print(f"  News Impact: {result.get('news_impact', 'NEUTRAL')}")
        print(f"  Confidence Adjustment: {result.get('confidence_adjustment', 0):+.2f}")
        print(f"  Should Skip: {result.get('should_skip', False)}")

        if result.get('should_skip'):
            print(f"  ✗ Signal REJECTED by news correlation")
            print(f"    This is why no trades are executing!")

    except Exception as e:
        print(f"  ✗ News correlation test failed: {e}")
    print()

print("=" * 60)
print("RECOMMENDATIONS:")
print("=" * 60)

if enable_consensus and available_validators < 2:
    print("1. Disable AI consensus temporarily:")
    print("   echo 'ENABLE_AI_CONSENSUS=false' >> .env")
    print()

if enable_consensus and available_validators < min_agreement:
    print("2. Lower minimum AI agreement:")
    print(f"   echo 'MIN_AI_AGREEMENT=1' >> .env")
    print()

if enable_news and not tavily_key:
    print("3. Disable news correlation (Tavily key missing):")
    print("   echo 'ENABLE_NEWS_CORRELATION=false' >> .env")
    print()

print("4. Check Railway logs for rejection reasons:")
print("   railway logs --tail 100")
print()
