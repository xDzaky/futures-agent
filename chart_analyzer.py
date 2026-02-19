"""
Chart & Signal Analyzer — AI-Powered Analysis
================================================
Combines multiple AI models for comprehensive analysis:
1. NVIDIA NIM Llama 3.2 90B Vision (FREE) — Chart image analysis
2. Groq Llama 3.3 70B (FREE)            — Text signal analysis + Indonesian text
3. Technical indicators                  — Confirmation layer

Takes raw Telegram messages (text + images) and produces
structured trade signals with confidence scores.

NOTE: Gemini replaced with NVIDIA NIM vision model because the Gemini API
key was reported as leaked (403 PERMISSION_DENIED). NVIDIA NIM is free-tier
and exposes an OpenAI-compatible API — no extra dependency needed beyond the
`openai` package that is already in requirements.txt.
"""

import os
import re
import json
import base64
import logging
import time
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("chart_analyzer")


class ChartAnalyzer:
    """
    Analyzes crypto signals from Telegram channels.
    Handles text analysis (Groq) and chart image analysis (NVIDIA NIM Vision).
    """

    def __init__(self):
        self.groq_key = os.getenv("GROQ_API_KEY", "")
        self.nvidia_key = os.getenv("NVIDIA_API_KEY", "")
        self.nvidia_vision_model = os.getenv(
            "NVIDIA_VISION_MODEL", "meta/llama-3.2-90b-vision-instruct"
        )
        self.nvidia_base_url = "https://integrate.api.nvidia.com/v1"

        # Initialize Groq (text analysis)
        self.groq_client = None
        if self.groq_key:
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=self.groq_key)
            except Exception as e:
                logger.warning(f"Groq init failed: {e}")

        # Initialize NVIDIA NIM (vision / chart image analysis)
        # Uses OpenAI-compatible API — no extra dependency needed.
        self.nvidia_client = None
        if self.nvidia_key:
            try:
                from openai import OpenAI
                self.nvidia_client = OpenAI(
                    base_url=self.nvidia_base_url,
                    api_key=self.nvidia_key,
                )
                logger.info("NVIDIA NIM vision client initialised ✓")
            except Exception as e:
                logger.warning(f"NVIDIA NIM init failed: {e}")

        # Rate limiting
        self._last_groq_call = 0
        self._last_nvidia_call = 0

    def analyze_message(self, message: Dict) -> Optional[Dict]:
        """
        Analyze a Telegram message (text + images) and extract trading signal.

        Args:
            message: {text, images: [bytes or path], channel, timestamp}

        Returns:
            {pair, side, entry, targets, stop_loss, leverage,
             confidence, reasoning, source_type} or None
        """
        text = message.get("text", "")
        images = message.get("images", [])
        channel = message.get("channel", "?")

        # Step 1: Analyze chart images with NVIDIA NIM vision
        image_analysis = None
        if images and self.nvidia_client:
            image_analysis = self._analyze_chart_image(images[0])
            if image_analysis:
                logger.info(f"Chart analysis: {image_analysis.get('summary', '')[:100]}")

        # Step 2: Analyze text with Groq (supports Indonesian)
        text_analysis = None
        if text and self.groq_client:
            text_analysis = self._analyze_text_signal(text, image_analysis)
            if text_analysis:
                logger.info(f"Text analysis: {text_analysis.get('action', 'SKIP')}")

        # Step 3: Combine results
        signal = self._combine_analyses(text, text_analysis, image_analysis, channel)
        return signal

    def _analyze_chart_image(self, image_data, mime_type: str = "image/jpeg") -> Optional[Dict]:
        """
        Analyze a chart image using NVIDIA NIM Llama 3.2 90B Vision.
        Can accept either a file path (str) or raw image bytes (bytes).

        NVIDIA NIM exposes an OpenAI-compatible /chat/completions endpoint.
        Images are sent as base64-encoded data URLs inside the message content.
        """
        if not self.nvidia_client:
            return None

        # Rate limit: 1 call per 4 seconds (conservative for free tier)
        now = time.time()
        wait = 4 - (now - self._last_nvidia_call)
        if wait > 0:
            time.sleep(wait)

        try:
            # ── Load image bytes ──────────────────────────────────────────
            if isinstance(image_data, str):
                with open(image_data, "rb") as f:
                    image_bytes = f.read()
                ext = image_data.lower().rsplit(".", 1)[-1]
                mime_type = {
                    "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "png": "image/png",  "webp": "image/webp",
                }.get(ext, "image/jpeg")
            else:
                image_bytes = image_data

            # ── Encode to base64 data URL ─────────────────────────────────
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            data_url = f"data:{mime_type};base64,{image_b64}"

            prompt = (
                "You are an expert crypto chart analyst. Analyze this trading chart image.\n\n"
                "Identify and respond with a JSON object:\n"
                "{\n"
                '    "pair": "BTC/USDT or whatever pair is shown",\n'
                '    "timeframe": "1h/4h/1d etc if visible",\n'
                '    "trend": "BULLISH/BEARISH/SIDEWAYS",\n'
                '    "pattern": "name of chart pattern if any (triangle, wedge, head-shoulders, channel, etc)",\n'
                '    "key_levels": {\n'
                '        "support": [list of support prices],\n'
                '        "resistance": [list of resistance prices]\n'
                "    },\n"
                '    "indicators": "describe any visible indicators (RSI, MACD, moving averages, volume)",\n'
                '    "signal": "LONG/SHORT/NEUTRAL",\n'
                '    "entry_zone": "price range for entry if applicable",\n'
                '    "targets": [list of target prices],\n'
                '    "stop_loss": "suggested stop loss level",\n'
                '    "confidence": 0.0-1.0,\n'
                '    "summary": "brief 1-2 sentence analysis"\n'
                "}\n\n"
                "Be specific about prices you can read from the chart. "
                "If you can't determine something, set it to null.\n"
                "IMPORTANT: Respond ONLY with the JSON object, no other text."
            )

            # ── Call NVIDIA NIM vision model ──────────────────────────────
            response = self.nvidia_client.chat.completions.create(
                model=self.nvidia_vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": data_url},
                            },
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
                max_tokens=1024,
                temperature=0.1,
            )

            self._last_nvidia_call = time.time()

            result_text = response.choices[0].message.content.strip()
            result = self._extract_json(result_text)
            if result:
                return result

        except Exception as e:
            logger.error(f"NVIDIA NIM chart analysis error: {e}")
            self._last_nvidia_call = time.time()

        return None

    def _analyze_text_signal(self, text: str, image_context: Optional[Dict] = None) -> Optional[Dict]:
        """Analyze signal text with Groq (supports Indonesian/English)."""
        if not self.groq_client:
            return self._keyword_based_analysis(text)  # Fallback

        # Rate limit with exponential backoff
        now = time.time()
        wait_time = max(0, 3 - (now - self._last_groq_call))
        if wait_time > 0:
            time.sleep(wait_time)

        try:
            context = ""
            if image_context:
                context = f"\nChart image analysis context: {json.dumps(image_context, default=str)}"

            prompt = f"""You are an expert crypto trading signal analyzer. Analyze this message from a Telegram crypto channel.
The message may be in Indonesian (Bahasa Indonesia) or English.

Message:
---
{text[:2000]}
---
{context}

Extract the trading signal and respond with a JSON object:
{{
    "action": "LONG/SHORT/NEWS/SKIP",
    "pair": "BTC/USDT etc",
    "entry": null or price number,
    "targets": [] or [list of target prices],
    "stop_loss": null or price number,
    "leverage": null or number,
    "confidence": 0.0-1.0,
    "sentiment": "BULLISH/BEARISH/NEUTRAL",
    "is_signal": true/false,
    "is_news": true/false,
    "reasoning": "brief explanation of the analysis",
    "key_info": "any critical market info extracted"
}}

Rules:
- If it's a clear BUY/LONG signal → action=LONG
- If it's a clear SELL/SHORT signal → action=SHORT
- If it's news/analysis without clear direction → action=NEWS
- If it's chat/spam/unrelated → action=SKIP
- Indonesian words: "naik/bullish/breakout/pump" = LONG, "turun/bearish/breakdown/dump" = SHORT
- "expecting turun" or "koreksi" = SHORT bias
- "breakout ke atas" = LONG bias
- Extract ALL price levels mentioned
- IMPORTANT: Respond ONLY with the JSON object"""

            response = self.groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=500,
            )

            self._last_groq_call = time.time()
            result_text = response.choices[0].message.content.strip()
            result = self._extract_json(result_text)
            if result:
                return result

        except Exception as e:
            error_msg = str(e)
            # Check for rate limit error
            if "429" in error_msg or "rate_limit" in error_msg.lower():
                logger.warning(f"Groq rate limit hit - using keyword fallback")
                # Extract wait time from error if available
                import re
                match = re.search(r'try again in ([\d.]+)s', error_msg)
                if match:
                    wait_seconds = float(match.group(1))
                    self._last_groq_call = time.time()  # Reset timer
                    logger.info(f"Will retry after {wait_seconds:.1f}s")
                return self._keyword_based_analysis(text)  # Fallback to keyword
            else:
                logger.error(f"Groq analysis error: {e}")
                self._last_groq_call = time.time()

        return None

    def _keyword_based_analysis(self, text: str) -> Optional[Dict]:
        """Fallback keyword-based analysis when Groq unavailable."""
        text_lower = text.lower()
        
        # Simple keyword detection
        long_words = ['long', 'buy', 'bullish', 'pump', 'naik', 'breakout', 'call']
        short_words = ['short', 'sell', 'bearish', 'dump', 'turun', 'breakdown', 'put']
        
        long_score = sum(1 for w in long_words if w in text_lower)
        short_score = sum(1 for w in short_words if w in text_lower)
        
        if long_score > short_score:
            action = "LONG"
            confidence = min(0.6, long_score * 0.15)
        elif short_score > long_score:
            action = "SHORT"
            confidence = min(0.6, short_score * 0.15)
        else:
            action = "SKIP"
            confidence = 0.3
        
        return {
            "action": action,
            "confidence": confidence,
            "is_signal": long_score > 0 or short_score > 0,
            "is_news": False,
            "reasoning": f"Keyword analysis: {long_score} long, {short_score} short keywords",
            "sentiment": "BULLISH" if action == "LONG" else "BEARISH" if action == "SHORT" else "NEUTRAL",
        }

    def _combine_analyses(self, raw_text: str, text_analysis: Optional[Dict],
                          image_analysis: Optional[Dict], channel: str) -> Optional[Dict]:
        """Combine text and image analysis into a final signal."""

        # If neither analysis worked, try basic parsing
        if not text_analysis and not image_analysis:
            return self._basic_parse(raw_text, channel)

        # Start with text analysis as base
        signal = {
            "pair": None,
            "side": None,
            "entry": None,
            "targets": [],
            "stop_loss": None,
            "leverage": None,
            "confidence": 0.5,
            "reasoning": "",
            "source": f"channel:{channel}",
            "source_type": "channel_ai",
        }

        # Extract from text analysis
        if text_analysis:
            action = text_analysis.get("action", "SKIP")
            if action in ("LONG", "SHORT"):
                signal["side"] = action
            elif action == "NEWS":
                # News = context only, not a signal
                signal["is_news"] = True
                signal["news_sentiment"] = text_analysis.get("sentiment", "NEUTRAL")
                signal["news_info"] = text_analysis.get("key_info", "")

            signal["pair"] = text_analysis.get("pair")
            signal["entry"] = text_analysis.get("entry")
            signal["targets"] = text_analysis.get("targets", [])
            signal["stop_loss"] = text_analysis.get("stop_loss")
            signal["leverage"] = text_analysis.get("leverage")
            signal["confidence"] = text_analysis.get("confidence", 0.5)
            signal["reasoning"] = text_analysis.get("reasoning", "")

        # Enhance with image analysis
        if image_analysis:
            img_signal = image_analysis.get("signal", "NEUTRAL")
            img_confidence = image_analysis.get("confidence", 0.5)

            # If image has a pair and text doesn't
            if not signal["pair"] and image_analysis.get("pair"):
                signal["pair"] = image_analysis["pair"]

            # If image agrees with text, boost confidence
            if signal["side"] and img_signal:
                text_dir = signal["side"]
                img_dir = img_signal
                if text_dir == img_dir:
                    # Agreement → boost confidence
                    signal["confidence"] = min(0.95, signal["confidence"] * 1.2)
                    signal["reasoning"] += " | Chart confirms direction"
                elif img_dir == "NEUTRAL":
                    pass  # No conflict
                else:
                    # Disagreement → reduce confidence
                    signal["confidence"] *= 0.6
                    signal["reasoning"] += f" | Chart shows {img_dir} (conflicts)"

            # If text has no direction but image does
            if not signal["side"] and img_signal in ("LONG", "SHORT"):
                signal["side"] = img_signal
                signal["confidence"] = img_confidence * 0.8

            # Use image targets/SL if text doesn't have them
            if not signal["targets"] and image_analysis.get("targets"):
                signal["targets"] = image_analysis["targets"]
            if not signal["stop_loss"] and image_analysis.get("stop_loss"):
                signal["stop_loss"] = image_analysis["stop_loss"]
            if not signal["entry"] and image_analysis.get("entry_zone"):
                try:
                    ez = image_analysis["entry_zone"]
                    if isinstance(ez, (int, float)):
                        signal["entry"] = float(ez)
                    elif isinstance(ez, str):
                        nums = re.findall(r'[\d.]+', ez)
                        if nums:
                            signal["entry"] = sum(float(n) for n in nums) / len(nums)
                except (ValueError, TypeError):
                    pass

            signal["chart_pattern"] = image_analysis.get("pattern")
            signal["chart_summary"] = image_analysis.get("summary")

        # Validate
        if not signal.get("side") or not signal.get("pair"):
            # Return as news context if we have useful info
            if signal.get("is_news"):
                return signal
            return None

        # Clean up pair format
        pair = signal["pair"]
        if pair:
            pair = pair.upper().replace(" ", "")
            if "/" not in pair:
                pair = pair.replace("USDT", "/USDT")
            if not pair.endswith("/USDT"):
                pair = pair + "/USDT"
            # Remove double USDT
            pair = pair.replace("/USDT/USDT", "/USDT")
            signal["pair"] = pair

        return signal

    def _basic_parse(self, text: str, channel: str) -> Optional[Dict]:
        """Fallback: basic regex parsing without AI."""
        from signal_scraper import SignalParser
        parser = SignalParser()
        result = parser.parse(text)
        if result:
            result["source"] = f"channel:{channel}"
            result["source_type"] = "channel_basic"
        return result

    def _extract_json(self, text: str) -> Optional[Dict]:
        """Extract JSON from a response that might have extra text."""
        text = text.strip()
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Find JSON block
        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        return None

    def analyze_news_context(self, messages: List[Dict]) -> Dict:
        """
        Analyze multiple news messages to build market context.
        Returns overall sentiment and key events.
        """
        if not self.groq_client or not messages:
            return {"sentiment": "NEUTRAL", "events": [], "summary": "No news"}

        # Combine recent news
        news_texts = []
        for msg in messages[-10:]:  # Last 10 messages
            text = msg.get("text", "")
            if text and len(text) > 20:
                channel = msg.get("channel", "?")
                news_texts.append(f"[{channel}] {text[:300]}")

        if not news_texts:
            return {"sentiment": "NEUTRAL", "events": [], "summary": "No news"}

        combined = "\n---\n".join(news_texts)

        try:
            prompt = f"""Analyze these crypto news messages from Telegram (may be in Indonesian/English).
Give overall market sentiment and key events.

Messages:
{combined[:3000]}

Respond with JSON:
{{
    "sentiment": "BULLISH/BEARISH/NEUTRAL",
    "confidence": 0.0-1.0,
    "events": ["key event 1", "key event 2"],
    "summary": "brief market summary",
    "pairs_mentioned": ["BTC", "ETH", etc],
    "risk_level": "LOW/MEDIUM/HIGH",
    "recommendation": "brief trading recommendation"
}}

Respond ONLY with JSON."""

            response = self.groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=500,
            )

            result_text = response.choices[0].message.content.strip()
            result = self._extract_json(result_text)
            if result:
                return result

        except Exception as e:
            logger.error(f"News analysis error: {e}")

        return {"sentiment": "NEUTRAL", "events": [], "summary": "Analysis failed"}


# ─── Test ──────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    analyzer = ChartAnalyzer()

    print(f"Groq:        {'OK' if analyzer.groq_client  else 'NOT CONFIGURED'}")
    print(f"NVIDIA NIM:  {'OK' if analyzer.nvidia_client else 'NOT CONFIGURED'}")

    # Test Indonesian text analysis
    test_messages = [
        {
            "text": """$BTC
Terlihat BTC ternyata melakukan breakout dari trendlinenya. tapi volumenya cukup lemah, dan justru volume merahnya cukup besar. expecting untuk turun terlebih dahulu. mungkin di area rectangle (yang ditandain panah) akan ada reaksi""",
            "images": [],
            "channel": "@MWcryptojournal",
        },
        {
            "text": """🚀 SIGNAL ALERT 🚀
📊 SOL/USDT LONG
💰 Entry: 85.00 - 86.50
🎯 TP1: 90.00
🎯 TP2: 95.00
🎯 TP3: 100.00
❌ SL: 82.00
📊 Leverage: 20x""",
            "images": [],
            "channel": "@binance_360",
        },
        {
            "text": """Market Update:
Bitcoin ETF inflows mencapai $500M hari ini. Institutional buying terus meningkat.
Fear & Greed Index naik ke 45 dari 38 kemarin.
Dominance BTC: 52.3%""",
            "images": [],
            "channel": "@crypto_news",
        },
    ]

    for msg in test_messages:
        print(f"\n{'='*50}")
        print(f"Channel: {msg['channel']}")
        print(f"Text: {msg['text'][:100]}...")
        result = analyzer.analyze_message(msg)
        if result:
            print(f"Result: {json.dumps(result, indent=2, default=str)}")
        else:
            print("Result: No signal detected")
