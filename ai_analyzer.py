"""
AI Analyzer — LLM-Powered Trading Analysis
==============================================
Uses Groq (FREE Llama 3.3 70B) to:
- Analyze technical indicators + news + sentiment
- Make LONG/SHORT/SKIP decisions
- Generate entry, SL, TP, leverage recommendations
- Provide reasoning for each trade
"""

import os
import json
import logging
import time
from typing import Dict, Optional
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("ai_analyzer")


class AIAnalyzer:
    """AI-powered trading analysis using Groq (free Llama 3.3 70B)."""

    def __init__(self):
        self.groq_key = os.getenv("GROQ_API_KEY", "")
        self.client = Groq(api_key=self.groq_key) if self.groq_key else None
        self.model = "llama-3.3-70b-versatile"
        self._rate_limit_wait = 0
        self.total_calls = 0

    def analyze_trade(self, symbol: str, technical: Dict,
                      market_ctx: Dict, news: str = "") -> Optional[Dict]:
        """
        Full AI analysis for a trading opportunity.
        Returns: {action, side, confidence, entry, sl, tp1, tp2, tp3, leverage, reasoning}
        """
        if not self.client:
            logger.error("No Groq API key")
            return None

        # Rate limit protection
        if self._rate_limit_wait > 0:
            time.sleep(self._rate_limit_wait)
            self._rate_limit_wait = 0

        prompt = self._build_prompt(symbol, technical, market_ctx, news)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1000,
                response_format={"type": "json_object"},
            )

            self.total_calls += 1
            text = response.choices[0].message.content
            result = json.loads(text)

            # Validate response
            if not self._validate_response(result):
                logger.warning(f"Invalid AI response for {symbol}")
                return None

            result["model"] = self.model
            return result

        except Exception as e:
            error_str = str(e).lower()
            if "rate_limit" in error_str or "429" in error_str:
                self._rate_limit_wait = 10
                logger.warning("Groq rate limited, waiting 10s")
            else:
                logger.error(f"AI analysis error: {e}")
            return None

    def _system_prompt(self) -> str:
        return """You are a conservative crypto futures trader focused on high win-rate setups.
You analyze technical indicators, market context, and news to make trading decisions.

CRITICAL RULES:
1. PRIORITIZE CAPITAL PRESERVATION. Only trade when the setup is A+ quality.
2. MINIMUM CONFIDENCE: 0.75 (75%). If below 75%, you MUST respond "SKIP".
3. RISK/REWARD: Target potential > 1.5R. If the move looks limited, SKIP.
4. Respond with valid JSON only.

TRADING CRITERIA (LONG):
- Price > EMA50 and EMA200 (uptrend)
- RSI not overbought (>70)
- MACD bullish cross confirmed
- Volume supporting the move
- No major resistance just overhead

TRADING CRITERIA (SHORT):
- Price < EMA50 and EMA200 (downtrend)
- RSI not oversold (<30)
- MACD bearish cross confirmed
- Volume supporting the move
- No major support just below

JSON FORMAT:
{
  "action": "LONG" or "SHORT" or "SKIP",
  "confidence": 0.0-1.0,
  "leverage": 2-10,
  "sl_pct": float (stop loss % from entry, max 2.5%),
  "tp1_pct": float (min 1.5x sl_pct),
  "tp2_pct": float (2.5x sl_pct),
  "tp3_pct": float (4.0x sl_pct),
  "reasoning": "Brief explanation"
}"""

    def _build_prompt(self, symbol: str, technical: Dict,
                      market_ctx: Dict, news: str) -> str:
        # Extract key technical data
        ta_score = technical.get("consensus_score", 50)
        ta_signal = technical.get("consensus", "SKIP")

        # Per-timeframe breakdown
        tf_summary = ""
        for tf, data in technical.get("timeframes", {}).items():
            tf_summary += (
                f"\n  {tf}: score={data.get('score', 50)} "
                f"signal={data.get('signal', 'SKIP')} "
                f"RSI={data.get('rsi', 50):.1f} "
                f"MACD={data.get('macd_cross', 'N/A')} "
                f"EMA={data.get('ema_cross', 'N/A')} "
                f"BB={data.get('bb_signal', 'N/A')} "
                f"Vol={data.get('volume_signal', 'N/A')}"
            )

        # Market context
        ob = market_ctx.get("orderbook", {})
        funding = market_ctx.get("funding", {})
        fg = market_ctx.get("fear_greed", {})
        cmc = market_ctx.get("coinmarketcap", {})
        price = market_ctx.get("price", 0)

        # Extract ATR for SL/TP calculation hint
        tf_5m = technical.get("timeframes", {}).get("5m", {})
        atr_pct = tf_5m.get("atr_pct", 1.0)
        
        # CoinMarketCap context
        cmc_str = ""
        if cmc:
            cmc_str = f"""
  CoinMarketCap Metrics:
    24h Volume: ${cmc.get('volume_24h', 0):,.0f}
    Volume Change 24h: {cmc.get('volume_change_24h', 0):.1f}%
    Price Change 1h: {cmc.get('percent_change_1h', 0):.2f}%
    Price Change 24h: {cmc.get('percent_change_24h', 0):.2f}%
    Price Change 7d: {cmc.get('percent_change_7d', 0):.2f}%
    Market Cap Dominance: {cmc.get('market_cap_dominance', 0):.2f}%
    CMC Signal: {cmc.get('signal', 'N/A')}"""

        prompt = f"""Analyze {symbol} for a potential futures trade:

CURRENT PRICE: ${price:,.2f}

TECHNICAL ANALYSIS (Multi-TF Consensus):
  Overall Score: {ta_score}/100 ({ta_signal})
  Timeframes:{tf_summary}

MARKET CONTEXT:
  Orderbook: imbalance={ob.get('imbalance', 0):.4f} ({ob.get('signal', 'N/A')})
  Funding Rate: {funding.get('rate', 0):.6f} ({funding.get('signal', 'N/A')})
  Fear & Greed: {fg.get('value', 50)} ({fg.get('classification', 'N/A')})
  ATR%: {atr_pct:.2f}%{cmc_str}

NEWS & SENTIMENT:
{news if news else '  No significant news detected.'}

Based on all data above, provide your trading decision as JSON:
{{
  "action": "LONG" or "SHORT" or "SKIP",
  "confidence": 0.0-1.0,
  "leverage": 2-20,
  "sl_pct": float (stop loss % from entry),
  "tp1_pct": float (TP1 % from entry),
  "tp2_pct": float (TP2 % from entry),
  "tp3_pct": float (TP3 % from entry),
  "reasoning": "Brief explanation of the trade setup"
}}"""
        return prompt

    def _validate_response(self, result: Dict) -> bool:
        required = ["action", "confidence", "reasoning"]
        for key in required:
            if key not in result:
                return False

        if result["action"] not in ("LONG", "SHORT", "SKIP"):
            return False

        conf = result.get("confidence", 0)
        if not (0 <= conf <= 1):
            return False

        return True

    def analyze_news_impact(self, headline: str, symbol: str) -> Optional[Dict]:
        """Quick AI analysis of news impact on a specific coin."""
        if not self.client:
            return None

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": (
                        "You are a crypto news analyst. Analyze the impact of "
                        "this news on the given cryptocurrency. Respond in JSON: "
                        '{"impact": "BULLISH/BEARISH/NEUTRAL", "severity": 1-10, '
                        '"affected_coins": ["BTC", ...], "reasoning": "..."}'
                    )},
                    {"role": "user", "content": (
                        f"News: {headline}\n"
                        f"Coin: {symbol}\n"
                        f"What is the likely price impact?"
                    )},
                ],
                temperature=0.2,
                max_tokens=300,
                response_format={"type": "json_object"},
            )
            self.total_calls += 1
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.debug(f"News analysis error: {e}")
            return None
