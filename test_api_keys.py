"""
Test All API Keys — Verification Script
=========================================
Tests all configured API keys to ensure they're working:
- CoinGecko
- CoinMarketCap
- CryptoCompare
- Alpha Vantage
- NewsAPI
- Finnhub
"""

import os
import sys
import requests
from dotenv import load_dotenv
from colorama import init, Fore, Style

init(autoreset=True)
load_dotenv()

def test_coingecko():
    """Test CoinGecko API"""
    print(f"\n{Fore.CYAN}Testing CoinGecko API...")
    api_key = os.getenv("COINGECKO_API_KEY", "")
    
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        headers = {}
        if api_key:
            headers["x-cg-pro-api-key"] = api_key
            print(f"{Fore.YELLOW}  API Key: {api_key[:10]}...")
        else:
            print(f"{Fore.YELLOW}  Using free tier (no API key)")
        
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            btc_price = data.get("bitcoin", {}).get("usd", 0)
            print(f"{Fore.GREEN}  ✓ CoinGecko API Working")
            print(f"{Fore.WHITE}  BTC Price: ${btc_price:,.2f}")
            return True
        else:
            print(f"{Fore.RED}  ✗ Failed: HTTP {resp.status_code}")
            print(f"{Fore.RED}  Response: {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"{Fore.RED}  ✗ Error: {e}")
        return False

def test_coinmarketcap():
    """Test CoinMarketCap API"""
    print(f"\n{Fore.CYAN}Testing CoinMarketCap API...")
    api_key = os.getenv("COINMARKETCAP_API_KEY", "")
    
    if not api_key:
        print(f"{Fore.YELLOW}  No API key found - skipping")
        return False
    
    print(f"{Fore.YELLOW}  API Key: {api_key[:10]}...")
    
    try:
        url = "https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/latest"
        headers = {
            "X-CMC_PRO_API_KEY": api_key,
            "Accept": "application/json"
        }
        params = {"symbol": "BTC", "convert": "USD"}
        
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("data", {}).get("BTC", [])
            if data and len(data) > 0:
                quote = data[0].get("quote", {}).get("USD", {})
                price = quote.get("price", 0)
                pct_24h = quote.get("percent_change_24h", 0)
                volume_24h = quote.get("volume_24h", 0)
                print(f"{Fore.GREEN}  ✓ CoinMarketCap API Working")
                print(f"{Fore.WHITE}  BTC Price: ${price:,.2f}")
                print(f"{Fore.WHITE}  24h Change: {pct_24h:+.2f}%")
                print(f"{Fore.WHITE}  24h Volume: ${volume_24h:,.0f}")
                return True
            else:
                print(f"{Fore.RED}  ✗ No data returned")
                return False
        else:
            print(f"{Fore.RED}  ✗ Failed: HTTP {resp.status_code}")
            print(f"{Fore.RED}  Response: {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"{Fore.RED}  ✗ Error: {e}")
        return False

def test_cryptocompare():
    """Test CryptoCompare API"""
    print(f"\n{Fore.CYAN}Testing CryptoCompare API...")
    api_key = os.getenv("CRYPTOCOMPARE_API_KEY", "")
    
    try:
        url = "https://min-api.cryptocompare.com/data/price?fsym=BTC&tsyms=USD"
        params = {}
        if api_key:
            params["api_key"] = api_key
            print(f"{Fore.YELLOW}  API Key: {api_key[:10]}...")
        else:
            print(f"{Fore.YELLOW}  Using free tier (no API key)")
        
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            btc_price = data.get("USD", 0)
            print(f"{Fore.GREEN}  ✓ CryptoCompare API Working")
            print(f"{Fore.WHITE}  BTC Price: ${btc_price:,.2f}")
            
            # Test news endpoint
            news_url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
            news_resp = requests.get(news_url, timeout=10)
            if news_resp.status_code == 200:
                news_data = news_resp.json().get("Data", [])
                print(f"{Fore.GREEN}  ✓ CryptoCompare News Working ({len(news_data)} articles)")
            
            return True
        else:
            print(f"{Fore.RED}  ✗ Failed: HTTP {resp.status_code}")
            print(f"{Fore.RED}  Response: {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"{Fore.RED}  ✗ Error: {e}")
        return False

def test_alphavantage():
    """Test Alpha Vantage API"""
    print(f"\n{Fore.CYAN}Testing Alpha Vantage API...")
    api_key = os.getenv("ALPHAVANTAGE_API_KEY", "")
    
    if not api_key:
        print(f"{Fore.YELLOW}  No API key found - skipping")
        return False
    
    print(f"{Fore.YELLOW}  API Key: {api_key[:10]}...")
    
    try:
        # Test with crypto endpoint
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "CURRENCY_EXCHANGE_RATE",
            "from_currency": "BTC",
            "to_currency": "USD",
            "apikey": api_key
        }
        
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if "Realtime Currency Exchange Rate" in data:
                exchange = data["Realtime Currency Exchange Rate"]
                btc_price = float(exchange.get("5. Exchange Rate", 0))
                print(f"{Fore.GREEN}  ✓ Alpha Vantage API Working")
                print(f"{Fore.WHITE}  BTC Price: ${btc_price:,.2f}")
                return True
            elif "Note" in data:
                print(f"{Fore.YELLOW}  ⚠ Rate limit reached")
                print(f"{Fore.YELLOW}  Note: {data['Note']}")
                return False
            else:
                print(f"{Fore.RED}  ✗ Unexpected response format")
                print(f"{Fore.RED}  Response: {data}")
                return False
        else:
            print(f"{Fore.RED}  ✗ Failed: HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"{Fore.RED}  ✗ Error: {e}")
        return False

def test_newsapi():
    """Test NewsAPI"""
    print(f"\n{Fore.CYAN}Testing NewsAPI...")
    api_key = os.getenv("NEWSAPI_KEY", "")
    
    if not api_key:
        print(f"{Fore.YELLOW}  No API key found - skipping")
        return False
    
    print(f"{Fore.YELLOW}  API Key: {api_key[:10]}...")
    
    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": "cryptocurrency bitcoin",
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 5,
            "apiKey": api_key,
        }
        
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            articles = data.get("articles", [])
            print(f"{Fore.GREEN}  ✓ NewsAPI Working")
            print(f"{Fore.WHITE}  Found {len(articles)} recent articles")
            if articles:
                print(f"{Fore.WHITE}  Latest: {articles[0].get('title', '')[:60]}...")
            return True
        else:
            print(f"{Fore.RED}  ✗ Failed: HTTP {resp.status_code}")
            print(f"{Fore.RED}  Response: {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"{Fore.RED}  ✗ Error: {e}")
        return False

def test_finnhub():
    """Test Finnhub API"""
    print(f"\n{Fore.CYAN}Testing Finnhub API...")
    api_key = os.getenv("FINNHUB_API_KEY", "")
    
    if not api_key:
        print(f"{Fore.YELLOW}  No API key found - skipping")
        return False
    
    print(f"{Fore.YELLOW}  API Key: {api_key[:10]}...")
    
    try:
        url = "https://finnhub.io/api/v1/news"
        params = {
            "category": "crypto",
            "token": api_key,
        }
        
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            print(f"{Fore.GREEN}  ✓ Finnhub API Working")
            print(f"{Fore.WHITE}  Found {len(data)} crypto news items")
            if data:
                print(f"{Fore.WHITE}  Latest: {data[0].get('headline', '')[:60]}...")
            return True
        else:
            print(f"{Fore.RED}  ✗ Failed: HTTP {resp.status_code}")
            print(f"{Fore.RED}  Response: {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"{Fore.RED}  ✗ Error: {e}")
        return False

def main():
    """Run all API tests"""
    print(f"{Fore.MAGENTA}{Style.BRIGHT}")
    print("=" * 60)
    print("  CRYPTO TRADING API KEYS VERIFICATION")
    print("=" * 60)
    
    results = {
        "CoinGecko": test_coingecko(),
        "CoinMarketCap": test_coinmarketcap(),
        "CryptoCompare": test_cryptocompare(),
        "Alpha Vantage": test_alphavantage(),
        "NewsAPI": test_newsapi(),
        "Finnhub": test_finnhub(),
    }
    
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}")
    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    
    working = 0
    total = 0
    
    for api, status in results.items():
        total += 1
        if status:
            working += 1
            print(f"{Fore.GREEN}  ✓ {api}")
        else:
            print(f"{Fore.RED}  ✗ {api}")
    
    print(f"\n{Fore.CYAN}  Working: {working}/{total} APIs")
    
    if working == total:
        print(f"{Fore.GREEN}{Style.BRIGHT}\n  All APIs are working! 🚀")
    elif working >= total * 0.7:
        print(f"{Fore.YELLOW}{Style.BRIGHT}\n  Most APIs working, some issues detected ⚠️")
    else:
        print(f"{Fore.RED}{Style.BRIGHT}\n  Multiple API issues detected ❌")
    
    print()

if __name__ == "__main__":
    main()
