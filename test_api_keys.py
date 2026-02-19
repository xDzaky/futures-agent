#!/usr/bin/env python3
"""
Test all API keys for futures-agent.
Run: python3 test_api_keys.py
"""

import os
from dotenv import load_dotenv

load_dotenv()


def test_groq():
    """Test Groq AI API - PRIMARY provider"""
    print("\n" + "="*60)
    print("🤖 TESTING GROQ AI API (PRIMARY)")
    print("="*60)

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        print("❌ GROQ_API_KEY not found in .env")
        return False

    try:
        from groq import Groq
        client = Groq(api_key=api_key)

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "What is 2+2? Reply with just the number."}],
            temperature=0.0,
            max_tokens=10
        )

        if response and response.choices:
            answer = response.choices[0].message.content.strip()
            print(f"✅ Groq API working - Response: {answer}")
            return True
        else:
            print("❌ Groq returned no response")
            return False

    except Exception as e:
        print(f"❌ Groq error: {e}")
        return False


def test_nvidia():
    """Test NVIDIA NIM API - Multiple models"""
    print("\n" + "="*60)
    print("🤖 TESTING NVIDIA NIM API")
    print("="*60)

    api_key = os.getenv("NVIDIA_API_KEY", "")
    if not api_key:
        print("❌ NVIDIA_API_KEY not found in .env")
        return False

    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url="https://integrate.api.nvidia.com/v1",
            timeout=45.0
        )

        # Test models (all tested & working)
        models_to_test = [
            ("deepseek-ai/deepseek-v3.1", "DeepSeek V3.1 - Trading Analysis"),
            ("meta/llama-3.3-70b-instruct", "Llama 3.3 70B - Validator"),
            ("meta/llama-3.2-90b-vision-instruct", "Llama 3.2 90B - Vision"),
        ]

        working = []
        for model, description in models_to_test:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "Say hi"}],
                    max_tokens=5,
                    timeout=20
                )
                print(f"✅ {description}: OK")
                working.append(model)
            except Exception as e:
                print(f"❌ {description}: {str(e)[:50]}")

        if working:
            print(f"\n✅ NVIDIA NIM working - {len(working)}/{len(models_to_test)} models available")
            return True
        else:
            print("\n❌ NVIDIA NIM - No models working")
            return False

    except Exception as e:
        print(f"❌ NVIDIA NIM error: {e}")
        return False


def test_huggingface():
    """Test Hugging Face Inference API"""
    print("\n" + "="*60)
    print("🤖 TESTING HUGGING FACE API (LAST RESORT)")
    print("="*60)

    api_key = os.getenv("HUGGINGFACE_API_KEY", "")
    if not api_key:
        print("❌ HUGGINGFACE_API_KEY not found in .env")
        return False

    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url="https://router.huggingface.co/v1",
            timeout=60.0
        )

        response = client.chat.completions.create(
            model="Qwen/Qwen2.5-72B-Instruct",
            messages=[{"role": "user", "content": "What is 2+2? Reply with just the number."}],
            temperature=0.0,
            max_tokens=10
        )

        if response and response.choices:
            answer = response.choices[0].message.content.strip()
            print(f"✅ Hugging Face API working - Response: {answer}")
            print(f"   Model: Qwen/Qwen2.5-72B-Instruct")
            return True
        else:
            print("❌ Hugging Face returned no response")
            return False

    except Exception as e:
        print(f"❌ Hugging Face error: {e}")
        return False


def test_tavily():
    """Test Tavily Search API"""
    print("\n" + "="*60)
    print("🔍 TESTING TAVILY SEARCH API")
    print("="*60)

    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        print("❌ TAVILY_API_KEY not found in .env")
        return False

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)

        result = client.search(
            query="Bitcoin price prediction 2025",
            max_results=2
        )

        if result and "results" in result:
            print(f"✅ Tavily API working - {len(result['results'])} results")
            return True
        else:
            print("❌ Tavily returned unexpected format")
            return False

    except Exception as e:
        print(f"❌ Tavily error: {e}")
        return False


def main():
    print("\n" + "🔑 " * 20)
    print("FUTURES AGENT API KEY TESTS")
    print("🔑 " * 20)

    results = {}

    # Test AI providers
    print("\n📌 AI PROVIDERS:")
    results["Groq (PRIMARY)"] = test_groq()
    results["NVIDIA NIM"] = test_nvidia()
    results["Hugging Face"] = test_huggingface()
    results["Tavily Search"] = test_tavily()

    # Summary
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for api, status in results.items():
        icon = "✅" if status else "❌"
        print(f"{icon} {api}")

    print(f"\n{passed}/{total} APIs working ({(passed/total)*100:.0f}%)")

    if passed == total:
        print("\n🎉 ALL APIs CONFIGURED CORRECTLY!")
        print("✅ AI Priority: Groq (30/min) > NVIDIA > HF (30/hour)")
        print("✅ Recommended models:")
        print("   - deepseek-ai/deepseek-v3.1 (trading analysis)")
        print("   - meta/llama-3.3-70b-instruct (validator)")
        print("   - meta/llama-3.2-90b-vision-instruct (chart images)")
    else:
        print("\n⚠️  Some APIs failed. Check your .env file.")

    print("\n" + "="*60)


if __name__ == "__main__":
    main()
