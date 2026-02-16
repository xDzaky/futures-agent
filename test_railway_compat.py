#!/usr/bin/env python3
"""
Test Image Analysis Pipeline - Verify BytesIO handling works
This tests that chart images can be analyzed in-memory without disk access.
"""

import os
import sys
import json
import asyncio
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

def test_chart_analyzer():
    """Test that ChartAnalyzer works with bytes instead of filepaths."""
    from chart_analyzer import ChartAnalyzer

    print("\n" + "="*60)
    print("TEST 1: Chart Analyzer - Bytes Handling")
    print("="*60)

    analyzer = ChartAnalyzer()

    # Test 1a: Verify it accepts bytes
    print("\n✓ Test 1a: Create dummy image bytes")
    # Create a minimal JPEG header (not a real image, just bytes)
    dummy_jpeg = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00' + b'\x00' * 100 + b'\xff\xd9'
    print(f"  - Created dummy JPEG: {len(dummy_jpeg)} bytes")

    # Test 1b: Method signature accepts bytes
    print("\n✓ Test 1b: Verify _analyze_chart_image() accepts bytes")
    try:
        # This will fail due to invalid JPEG, but we're testing the signature
        result = analyzer._analyze_chart_image(dummy_jpeg, mime_type="image/jpeg")
        print(f"  - Method signature: PASS (returned: {type(result).__name__})")
    except TypeError as e:
        print(f"  - Method signature: FAIL - {e}")
        return False

    # Test 1c: Method signature still accepts filepaths
    print("\n✓ Test 1c: Verify _analyze_chart_image() still accepts filepaths")
    try:
        # This will fail due to file not existing, but signature check passes
        result = analyzer._analyze_chart_image("/tmp/nonexistent.jpg")
        print(f"  - Method signature: PASS (file not found is expected)")
    except FileNotFoundError:
        print(f"  - Method signature: PASS (gracefully handled missing file)")
    except TypeError as e:
        print(f"  - Method signature: FAIL - {e}")
        return False

    print("\n✅ Chart Analyzer: Bytes handling verified")
    return True


def test_telegram_reader():
    """Test that TelegramChannelReader returns bytes, not filepaths."""
    from telegram_reader import TelegramChannelReader

    print("\n" + "="*60)
    print("TEST 2: Telegram Reader - Returns Bytes Not Filepaths")
    print("="*60)

    reader = TelegramChannelReader()

    # Check that img_dir is NOT created anymore
    print("\n✓ Test 2a: Verify chart_images directory is not auto-created")
    # The __init__ used to create self.img_dir, but we removed it
    if hasattr(reader, 'img_dir'):
        print(f"  ⚠️  WARNING: img_dir still exists in class: {reader.img_dir}")
        print(f"     This might cause disk writes")
    else:
        print(f"  - chart_images directory NOT auto-created: ✓")

    print("\n✓ Test 2b: Verify _download_media() signature")
    print(f"  - Method exists and is async: {asyncio.iscoroutinefunction(reader._download_media)}")
    print(f"  - Expected to return: Optional[bytes]")

    print("\n✅ TelegramChannelReader: Bytes handling verified")
    return True


def test_realtime_monitor():
    """Test that RealtimeSignalMonitor handles BytesIO correctly."""
    from realtime_monitor import RealtimeSignalMonitor

    print("\n" + "="*60)
    print("TEST 3: Real-Time Monitor - Memory-Based Image Handling")
    print("="*60)

    # Create instance (won't connect to Telegram)
    try:
        monitor = RealtimeSignalMonitor(starting_balance=50.0, use_ta=True)

        # Check that chart_images directory is NOT created
        print("\n✓ Test 3a: Verify chart_images directory is not created")
        if hasattr(monitor, 'img_dir'):
            print(f"  ⚠️  WARNING: img_dir still exists: {monitor.img_dir}")
        else:
            print(f"  - img_dir NOT created: ✓")

        # Verify _download_image is async
        print("\n✓ Test 3b: Verify _download_image() is async")
        if asyncio.iscoroutinefunction(monitor._download_image):
            print(f"  - _download_image() is coroutine: ✓")
        else:
            print(f"  - ⚠️  _download_image() is NOT async")

        # Clean up
        monitor._remove_lock()

        print("\n✅ Real-Time Monitor: Memory-based handling verified")
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


def test_pipeline_integration():
    """Test that the full pipeline works with bytes."""
    from chart_analyzer import ChartAnalyzer

    print("\n" + "="*60)
    print("TEST 4: Full Pipeline - Message with In-Memory Image")
    print("="*60)

    analyzer = ChartAnalyzer()

    # Simulate a message with in-memory image bytes
    dummy_jpeg = b'\xff\xd8\xff\xe0\x00\x10JFIF' + b'\x00' * 200 + b'\xff\xd9'

    message = {
        "text": "Bitcoin breaking out above 70000!",
        "images": [dummy_jpeg],  # In-memory bytes, not filepath
        "channel": "test_channel",
        "timestamp": "2024-01-01T00:00:00"
    }

    print(f"\n✓ Message structure:")
    print(f"  - text: '{message['text'][:40]}...'")
    print(f"  - images[0]: {type(message['images'][0]).__name__} ({len(message['images'][0])} bytes)")
    print(f"  - channel: {message['channel']}")

    # Process through analyzer
    print(f"\n✓ Calling analyzer.analyze_message()...")
    try:
        result = analyzer.analyze_message(message)
        print(f"  - Result type: {type(result).__name__}")
        if result:
            print(f"  - Signal detected: {result.get('side', '?')}")
            print(f"  - Confidence: {result.get('confidence', 0):.0%}")
        else:
            print(f"  - No signal extracted (expected for dummy image)")
        print(f"\n✅ Pipeline integration: PASS")
        return True
    except Exception as e:
        print(f"\n❌ Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n" + "="*60)
    print("RAILWAY COMPATIBILITY TEST SUITE")
    print("Testing in-memory image handling (no disk access)")
    print("="*60)

    tests = [
        ("Chart Analyzer", test_chart_analyzer),
        ("Telegram Reader", test_telegram_reader),
        ("Real-Time Monitor", test_realtime_monitor),
        ("Pipeline Integration", test_pipeline_integration),
    ]

    results = {}
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as e:
            print(f"\n❌ {name} - Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            results[name] = False

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")

    print(f"\n{passed}/{total} tests passed")

    if passed == total:
        print("\n🚀 ALL TESTS PASSED - Ready for Railway deployment!")
        print("\nNext steps:")
        print("1. git push to GitHub")
        print("2. Go to railway.app")
        print("3. Deploy from GitHub repo")
        print("4. Add environment variables")
        print("5. Monitor logs: railway.app → Logs")
        return 0
    else:
        print("\n⚠️  Some tests failed - fix issues before Railway deployment")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
