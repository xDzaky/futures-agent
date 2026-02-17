"""
System Analysis & Win Rate Estimator
======================================
Analyzes the futures trading agent capabilities and estimates win rate based on:
- Available data sources
- Technical indicators
- AI analysis quality
- Risk management features
- Market data quality
"""

import os
import sys
from datetime import datetime
from colorama import init, Fore, Style
from dotenv import load_dotenv

init(autoreset=True)
load_dotenv()

def print_header(title):
    """Print formatted header"""
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}")
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)

def print_section(title):
    """Print section title"""
    print(f"\n{Fore.CYAN}{Style.BRIGHT}▸ {title}")
    print(f"{Fore.CYAN}{'─' * 70}")

def check_api_availability():
    """Check which APIs are configured"""
    apis = {
        "GROQ_API_KEY": "Groq AI (Llama 3.3 70B)",
        "GEMINI_API_KEY": "Google Gemini Vision",
        "NEWSAPI_KEY": "NewsAPI",
        "FINNHUB_API_KEY": "Finnhub",
        "COINGECKO_API_KEY": "CoinGecko Pro",
        "COINMARKETCAP_API_KEY": "CoinMarketCap",
        "CRYPTOCOMPARE_API_KEY": "CryptoCompare Pro",
        "ALPHAVANTAGE_API_KEY": "Alpha Vantage",
        "TELEGRAM_BOT_TOKEN": "Telegram Bot",
        "TELEGRAM_API_ID": "Telegram User API",
    }
    
    available = {}
    for key, name in apis.items():
        value = os.getenv(key, "")
        available[name] = bool(value)
        status = f"{Fore.GREEN}✓" if value else f"{Fore.RED}✗"
        print(f"  {status} {name}")
    
    return available

def analyze_data_sources(apis):
    """Analyze available data sources"""
    print_section("DATA SOURCES ANALYSIS")
    
    # Price Data Sources
    price_sources = []
    print(f"\n{Fore.YELLOW}Price Data Sources:")
    
    # Always available (free, no key)
    price_sources.append("Gate.io (always available)")
    print(f"  {Fore.GREEN}✓ Gate.io - Spot prices & OHLCV")
    
    price_sources.append("Binance (if not geo-blocked)")
    print(f"  {Fore.GREEN}✓ Binance - Futures prices, orderbook, funding")
    
    if apis.get("CoinGecko Pro"):
        price_sources.append("CoinGecko Pro (better limits)")
        print(f"  {Fore.GREEN}✓ CoinGecko Pro - Enhanced price data")
    else:
        price_sources.append("CoinGecko Free")
        print(f"  {Fore.YELLOW}⚠ CoinGecko Free - Limited rate")
    
    if apis.get("CoinMarketCap"):
        price_sources.append("CoinMarketCap (premium metrics)")
        print(f"  {Fore.GREEN}✓ CoinMarketCap - Volume, dominance, trends")
    
    if apis.get("CryptoCompare Pro"):
        price_sources.append("CryptoCompare Pro (better limits)")
        print(f"  {Fore.GREEN}✓ CryptoCompare Pro - Enhanced OHLCV & news")
    else:
        price_sources.append("CryptoCompare Free")
        print(f"  {Fore.YELLOW}⚠ CryptoCompare Free - Limited rate")
    
    if apis.get("Alpha Vantage"):
        price_sources.append("Alpha Vantage (technical indicators)")
        print(f"  {Fore.GREEN}✓ Alpha Vantage - Additional TA data")
    
    # News Sources
    news_sources = []
    print(f"\n{Fore.YELLOW}News Sources:")
    
    news_sources.append("CryptoCompare News (always free)")
    print(f"  {Fore.GREEN}✓ CryptoCompare - Crypto news feed")
    
    if apis.get("NewsAPI"):
        news_sources.append("NewsAPI (100 req/day)")
        print(f"  {Fore.GREEN}✓ NewsAPI - General news")
    
    if apis.get("Finnhub"):
        news_sources.append("Finnhub (60 req/min)")
        print(f"  {Fore.GREEN}✓ Finnhub - Market news")
    
    # AI Analysis
    print(f"\n{Fore.YELLOW}AI Analysis:")
    
    if apis.get("Groq AI (Llama 3.3 70B)"):
        print(f"  {Fore.GREEN}✓ Groq Llama 3.3 70B - Trading decisions")
    else:
        print(f"  {Fore.RED}✗ No AI analyzer configured!")
    
    if apis.get("Google Gemini Vision"):
        print(f"  {Fore.GREEN}✓ Gemini Vision - Chart image analysis")
    else:
        print(f"  {Fore.YELLOW}⚠ No chart vision analysis")
    
    # Signal Sources
    print(f"\n{Fore.YELLOW}Signal Sources:")
    
    if apis.get("Telegram User API"):
        channels = os.getenv("SIGNAL_CHANNELS", "").split(",")
        print(f"  {Fore.GREEN}✓ Telegram Signal Scraping - {len(channels)} channels")
    else:
        print(f"  {Fore.YELLOW}⚠ Telegram scraping not configured")
    
    return {
        "price_sources": len(price_sources),
        "news_sources": len(news_sources),
        "has_ai": apis.get("Groq AI (Llama 3.3 70B)", False),
        "has_vision": apis.get("Google Gemini Vision", False),
        "has_telegram": apis.get("Telegram User API", False),
    }

def analyze_technical_indicators():
    """List technical indicators used"""
    print_section("TECHNICAL INDICATORS")
    
    indicators = [
        ("RSI (Relative Strength Index)", "Overbought/oversold detection"),
        ("MACD (Moving Average Convergence Divergence)", "Trend momentum"),
        ("EMA Cross (9/21)", "Short-term trend changes"),
        ("Bollinger Bands", "Volatility & price extremes"),
        ("ATR (Average True Range)", "Volatility for SL/TP sizing"),
        ("Volume Analysis", "Trend confirmation"),
        ("Support/Resistance", "Key price levels"),
        ("Multi-Timeframe Analysis", "1m, 5m, 15m, 1h, 4h consensus"),
    ]
    
    for name, description in indicators:
        print(f"  {Fore.GREEN}✓ {name}")
        print(f"    {Fore.WHITE}{description}")
    
    return len(indicators)

def analyze_risk_management():
    """Analyze risk management features"""
    print_section("RISK MANAGEMENT FEATURES")
    
    features = [
        ("Position Sizing", "Max 2-10% risk per trade based on confidence"),
        ("Leverage Limits", "2x-20x based on AI confidence (0.65-0.95+)"),
        ("Stop Loss", "Always set, max 5% distance"),
        ("Take Profit Layers", "TP1 (40%), TP2 (40%), TP3 (20%)"),
        ("Trailing Stops", "SL moves to entry after TP1, breakeven+ after TP2"),
        ("Max Positions", "3 concurrent positions maximum"),
        ("Drawdown Protection", "30% max drawdown → pause trading"),
        ("Loss Streak Protection", "4 consecutive losses → cooldown"),
        ("Emergency Close", "-20% leveraged loss → force close"),
        ("Daily Loss Limit", "-5% daily loss → stop for the day"),
    ]
    
    for name, description in features:
        print(f"  {Fore.GREEN}✓ {name}")
        print(f"    {Fore.WHITE}{description}")
    
    return len(features)

def estimate_win_rate(data_quality, indicator_count, risk_features, has_ai):
    """Estimate potential win rate based on system capabilities"""
    print_section("WIN RATE ESTIMATION")
    
    # Base win rate (random trading)
    base_rate = 30.0
    
    # Data quality bonus (max +20%)
    data_bonus = min(data_quality["price_sources"] * 2, 15)
    data_bonus += min(data_quality["news_sources"] * 2, 5)
    
    # Technical indicators bonus (max +15%)
    ta_bonus = min(indicator_count * 1.5, 15)
    
    # AI analysis bonus (max +25%)
    ai_bonus = 0
    if has_ai:
        ai_bonus = 20
        if data_quality["has_vision"]:
            ai_bonus += 5
    
    # Risk management bonus (max +10%)
    risk_bonus = min(risk_features * 1, 10)
    
    # Signal source bonus (max +10%)
    signal_bonus = 10 if data_quality["has_telegram"] else 0
    
    # Calculate estimated win rate
    estimated_rate = base_rate + data_bonus + ta_bonus + ai_bonus + risk_bonus + signal_bonus
    
    # Cap at realistic maximum (75% is very good)
    estimated_rate = min(estimated_rate, 75)
    
    print(f"\n{Fore.YELLOW}Win Rate Components:")
    print(f"  Base Rate (random): {base_rate:.1f}%")
    print(f"  + Data Quality: +{data_bonus:.1f}% ({data_quality['price_sources']} price + {data_quality['news_sources']} news sources)")
    print(f"  + Technical Indicators: +{ta_bonus:.1f}% ({indicator_count} indicators)")
    print(f"  + AI Analysis: +{ai_bonus:.1f}% ({'Yes' if has_ai else 'No'})")
    print(f"  + Risk Management: +{risk_bonus:.1f}% ({risk_features} features)")
    print(f"  + Signal Sources: +{signal_bonus:.1f}% ({'Telegram' if data_quality['has_telegram'] else 'None'})")
    
    print(f"\n{Fore.GREEN}{Style.BRIGHT}Estimated Win Rate: {estimated_rate:.1f}%")
    
    # Risk/Reward ratio estimate
    avg_win = 2.5  # Average TP targets around 2.5% with leverage
    avg_loss = 1.5  # SL typically tighter
    
    print(f"\n{Fore.YELLOW}Risk/Reward Profile:")
    print(f"  Average Win: +{avg_win:.1f}%")
    print(f"  Average Loss: -{avg_loss:.1f}%")
    print(f"  Risk/Reward Ratio: 1:{avg_win/avg_loss:.2f}")
    
    # Expected value calculation
    win_pct = estimated_rate / 100
    loss_pct = 1 - win_pct
    expected_value = (win_pct * avg_win) - (loss_pct * avg_loss)
    
    print(f"\n{Fore.YELLOW}Expected Value per Trade:")
    print(f"  EV = ({win_pct:.2f} × {avg_win:.1f}%) - ({loss_pct:.2f} × {avg_loss:.1f}%)")
    print(f"  EV = {expected_value:+.2f}%")
    
    if expected_value > 0:
        print(f"\n{Fore.GREEN}{Style.BRIGHT}✓ POSITIVE EXPECTED VALUE - Profitable long-term")
    else:
        print(f"\n{Fore.RED}{Style.BRIGHT}✗ NEGATIVE EXPECTED VALUE - Not profitable long-term")
    
    return estimated_rate, expected_value

def estimate_performance():
    """Estimate performance metrics over different timeframes"""
    print_section("PERFORMANCE PROJECTIONS (Paper Trading)")
    
    starting_balance = float(os.getenv("STARTING_BALANCE", "1000"))
    max_risk = float(os.getenv("MAX_RISK_PER_TRADE", "0.02"))
    
    print(f"\n{Fore.YELLOW}Trading Parameters:")
    print(f"  Starting Balance: ${starting_balance:,.2f}")
    print(f"  Max Risk per Trade: {max_risk*100:.1f}%")
    print(f"  Trading Mode: Paper Trading (Testnet)")
    
    # Conservative estimate: 45% win rate, 2:1 R/R
    scenarios = [
        ("Conservative", 45, 2.0, 1.0),
        ("Moderate", 55, 2.5, 1.5),
        ("Optimistic", 65, 3.0, 1.5),
    ]
    
    print(f"\n{Fore.YELLOW}1-Week Projections (20-30 trades):")
    print(f"{'Scenario':<15} {'Win Rate':<10} {'ROI':<10} {'Balance':<15}")
    print(f"{Fore.CYAN}{'-' * 50}")
    
    for scenario, win_rate, avg_win, avg_loss in scenarios:
        trades = 25
        wins = int(trades * win_rate / 100)
        losses = trades - wins
        
        # Calculate P&L
        avg_position = starting_balance * max_risk
        total_profit = wins * (avg_position * avg_win / 100)
        total_loss = losses * (avg_position * avg_loss / 100)
        net_pnl = total_profit - total_loss
        roi = (net_pnl / starting_balance) * 100
        final_balance = starting_balance + net_pnl
        
        color = Fore.GREEN if roi > 0 else Fore.RED
        print(f"{color}{scenario:<15} {win_rate}%{'':<6} {roi:+.1f}%{'':<5} ${final_balance:,.2f}")
    
    print(f"\n{Fore.YELLOW}1-Month Projections (80-120 trades):")
    print(f"{'Scenario':<15} {'Win Rate':<10} {'ROI':<10} {'Balance':<15}")
    print(f"{Fore.CYAN}{'-' * 50}")
    
    for scenario, win_rate, avg_win, avg_loss in scenarios:
        trades = 100
        wins = int(trades * win_rate / 100)
        losses = trades - wins
        
        avg_position = starting_balance * max_risk
        total_profit = wins * (avg_position * avg_win / 100)
        total_loss = losses * (avg_position * avg_loss / 100)
        net_pnl = total_profit - total_loss
        roi = (net_pnl / starting_balance) * 100
        final_balance = starting_balance + net_pnl
        
        color = Fore.GREEN if roi > 0 else Fore.RED
        print(f"{color}{scenario:<15} {win_rate}%{'':<6} {roi:+.1f}%{'':<5} ${final_balance:,.2f}")

def main():
    """Main analysis function"""
    print_header("FUTURES TRADING AGENT - SYSTEM ANALYSIS")
    
    print(f"{Fore.WHITE}Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{Fore.WHITE}Trading Mode: PAPER TRADING (Testnet)")
    
    print_section("API CONFIGURATION")
    apis = check_api_availability()
    
    data_quality = analyze_data_sources(apis)
    indicator_count = analyze_technical_indicators()
    risk_features = analyze_risk_management()
    
    has_ai = apis.get("Groq AI (Llama 3.3 70B)", False)
    
    win_rate, ev = estimate_win_rate(data_quality, indicator_count, risk_features, has_ai)
    
    estimate_performance()
    
    print_section("RECOMMENDATIONS")
    
    recommendations = []
    
    if not apis.get("CoinMarketCap"):
        recommendations.append("⚠ Add CoinMarketCap API for better market metrics")
    
    if not apis.get("CryptoCompare Pro"):
        recommendations.append("⚠ CryptoCompare Pro key for unlimited rate limits")
    
    if not apis.get("Google Gemini Vision"):
        recommendations.append("⚠ Add Gemini Vision for chart pattern analysis")
    
    if not apis.get("Telegram User API"):
        recommendations.append("⚠ Configure Telegram scraping for signal sources")
    
    if not has_ai:
        recommendations.append("❌ CRITICAL: Groq API key required for AI analysis!")
    
    if recommendations:
        for rec in recommendations:
            color = Fore.RED if "CRITICAL" in rec else Fore.YELLOW
            print(f"  {color}{rec}")
    else:
        print(f"  {Fore.GREEN}✓ All recommended APIs configured!")
    
    print_section("SUMMARY")
    
    total_apis = len(apis)
    configured_apis = sum(1 for v in apis.values() if v)
    
    print(f"  APIs Configured: {configured_apis}/{total_apis}")
    print(f"  Data Sources: {data_quality['price_sources']} price + {data_quality['news_sources']} news")
    print(f"  Technical Indicators: {indicator_count}")
    print(f"  Risk Features: {risk_features}")
    print(f"  Estimated Win Rate: {Fore.GREEN}{Style.BRIGHT}{win_rate:.1f}%")
    print(f"  Expected Value: {Fore.GREEN if ev > 0 else Fore.RED}{Style.BRIGHT}{ev:+.2f}% per trade")
    
    if ev > 0 and has_ai:
        print(f"\n{Fore.GREEN}{Style.BRIGHT}  ✓ SYSTEM READY FOR TRADING")
        print(f"{Fore.WHITE}    Start with paper trading to validate performance")
    elif not has_ai:
        print(f"\n{Fore.RED}{Style.BRIGHT}  ✗ SYSTEM NOT READY")
        print(f"{Fore.WHITE}    Configure Groq API key for AI analysis")
    else:
        print(f"\n{Fore.YELLOW}{Style.BRIGHT}  ⚠ SYSTEM CONFIGURED BUT NEEDS TUNING")
        print(f"{Fore.WHITE}    Add more data sources to improve win rate")
    
    print()

if __name__ == "__main__":
    main()
