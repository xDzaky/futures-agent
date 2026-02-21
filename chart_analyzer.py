"""
Chart & Signal Analyzer — AI-Powered Analysis
================================================
Multi-AI consensus for comprehensive analysis:

AI Model Priority (tested & working):
1. Groq Llama 3.3 70B (PRIMARY)     — Text signal analysis, 30 req/min
2. NVIDIA DeepSeek V3.1             — Trading analysis, ~30 req/min
3. NVIDIA Llama-3.3-70B             — Cross-validator
4. NVIDIA Llama-3.2-90B-Vision      — Chart image analysis
5. HF Qwen2.5-72B (LAST RESORT)     — Emergency fallback, 30 req/hour

Takes raw Telegram messages (text + images) and produces
structured trade signals with confidence scores.

NOTE: Gemini replaced with NVIDIA NIM vision model because the Gemini API
key was reported as leaked (403 PERMISSION_DENIED). NVIDIA NIM is free-tier
and exposes an OpenAI-compatible API — no extra dependency needed beyond the
`openai` package that is already in requirements.txt.

Tested NVIDIA Models (11 working):
- deepseek-ai/deepseek-v3.1 ✅ (best for trading analysis)
- meta/llama-3.3-70b-instruct ✅ (cross-validator)
- meta/llama-3.1-70b-instruct ✅ (alternative validator)
- qwen/qwen2.5-coder-32b-instruct ✅ (structured analysis)
- google/gemma-2-9b-it ✅ (fast analysis)
- microsoft/phi-3-mini-4k-instruct ✅ (quick responses)
- meta/llama-3.2-90b-vision-instruct ✅ (chart images)
"""

import os
import re
import json
import base64
import logging
import time
from typing import Dict, List, Optional
from dotenv import load_dotenv

# New Google GenAI SDK
try:
    from google import genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

# Macro Intuition System
try:
    from macro_context import get_macro_system_prompt, get_macro_summary
    HAS_MACRO = True
except ImportError:
    HAS_MACRO = False
    def get_macro_system_prompt(): return ""
    def get_macro_summary(): return {"status": "NO_MODULE"}

load_dotenv()
logger = logging.getLogger("chart_analyzer")


class ChartAnalyzer:
    """
    Analyzes crypto signals from Telegram channels.
    Handles text analysis (Groq) and chart image analysis (NVIDIA NIM Vision).
    Multi-AI consensus for better accuracy.
    """

    def __init__(self):
        # Gemini API Key Rotation logic
        self.gemini_keys = [k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()]
        if not self.gemini_keys and os.getenv("GEMINI_API_KEY"):
            self.gemini_keys = [os.getenv("GEMINI_API_KEY")]
        
        self.current_gemini_idx = 0
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        
        # Groq API Key Rotation
        self.groq_keys = [k.strip() for k in os.getenv("GROQ_API_KEYS", "").split(",") if k.strip()]
        if not self.groq_keys and os.getenv("GROQ_API_KEY"):
            self.groq_keys = [os.getenv("GROQ_API_KEY")]
        self.current_groq_idx = 0

        # NVIDIA API Key Rotation
        self.nvidia_keys = [k.strip() for k in os.getenv("NVIDIA_API_KEYS", "").split(",") if k.strip()]
        if not self.nvidia_keys and os.getenv("NVIDIA_API_KEY"):
            self.nvidia_keys = [os.getenv("NVIDIA_API_KEY")]
        self.current_nvidia_idx = 0

        self.hf_key = os.getenv("HUGGINGFACE_API_KEY", "")
        
        # ... fallback models
        self.nvidia_vision_model = os.getenv("NVIDIA_VISION_MODEL", "meta/llama-3.2-90b-vision-instruct")
        self.nvidia_analysis_model = os.getenv("NVIDIA_ANALYSIS_MODEL", "deepseek-ai/deepseek-v3.1")
        self.nvidia_validator_model = os.getenv("NVIDIA_VALIDATOR_MODEL", "meta/llama-3.3-70b-instruct")
        self.nvidia_base_url = "https://integrate.api.nvidia.com/v1"
        self.hf_base_url = "https://router.huggingface.co/v1"
        self.hf_model = "Qwen/Qwen2.5-72B-Instruct"

        # Initialize fallback clients with multi-key rotation
        # ── Cooldown state (persists across key rotations!) ──
        self._gemini_cooldown_until = 0
        self._gemini_cooldown_duration = 120  # 2 menit
        self._groq_cooldown_until = 0
        self._groq_cooldown_duration = 3600   # 1 jam (daily limit = harus tunggu sampai reset)
        self._last_groq_call = 0
        self._last_nvidia_call = 0
        self._last_hf_call = 0

        # Groq daily usage tracker: {key_idx: request_count}
        self._groq_key_errors: dict = {}  # track which keys have hit limits

        self._init_fallback_clients()

    def _init_fallback_clients(self):
        """Initialize/refresh client objects only (do NOT reset cooldown state)."""
        from groq import Groq
        from openai import OpenAI

        g_key = self.groq_keys[self.current_groq_idx] if self.groq_keys else None
        n_key = self.nvidia_keys[self.current_nvidia_idx] if self.nvidia_keys else None

        self.groq_client = Groq(api_key=g_key) if g_key else None
        self.nvidia_client = OpenAI(api_key=n_key, base_url=self.nvidia_base_url) if n_key else None
        self.hf_client = OpenAI(api_key=self.hf_key, base_url=self.hf_base_url) if self.hf_key else None

        logger.debug(f"Groq client init: key_idx={self.current_groq_idx} (/{len(self.groq_keys)})")

    def _get_gemini_client(self):
        """Get Gemini client with rotation."""
        if not HAS_GEMINI or not self.gemini_keys:
            return None
        
        key = self.gemini_keys[self.current_gemini_idx]
        return genai.Client(api_key=key)

    def analyze_message(self, message: Dict) -> Optional[Dict]:
        """
        Analyze a Telegram message using Multi-modal Gemini with Fallback.
        """
        text = message.get("text", "")
        images = message.get("images", [])
        channel = message.get("channel", "?")

        # STRATEGY 1: Attempt Multi-modal Analysis with Gemini (Tier 1)
        if HAS_GEMINI and self.gemini_keys:
            result = self._analyze_with_gemini_multimodal(text, images)
            if result:
                # Add source info
                result["source"] = f"channel:{channel}"
                result["source_type"] = "gemini_multimodal"
                return result
        
        # STRATEGY 2: Fallback to NVIDIA NIM + Groq (Tier 2)
        logger.info("Gemini failed/unavailable, falling back to NVIDIA + Groq")
        
        image_analysis = None
        if images and self.nvidia_client:
            image_analysis = self._analyze_chart_image(images[0])

        text_analysis = None
        if text and self.groq_client:
            text_analysis = self._analyze_text_signal(text, image_analysis)

        return self._combine_analyses(text, text_analysis, image_analysis, channel)

    def _analyze_with_gemini_multimodal(self, text: str, images: List) -> Optional[Dict]:
        """Performs multi-modal analysis using Gemini 2.x with Key Rotation + Macro Intuition."""
        
        # ── Cek Cooldown Gemini ──
        if time.time() < self._gemini_cooldown_until:
            remaining = int(self._gemini_cooldown_until - time.time())
            logger.debug(f"Gemini sedang dalam cooldown ({remaining}s tersisa). Langsung fallback.")
            return None

        max_retries = len(self.gemini_keys)

        # ── Load Macro Context (Intuisi Makro) ────────────────────────────
        macro_prompt = get_macro_system_prompt()
        if macro_prompt:
            macro_summary = get_macro_summary()
            logger.info(f"📊 Macro context: {macro_summary.get('files', 0)} file(s), "
                        f"{macro_summary.get('chars', 0)} chars, "
                        f"latest: {macro_summary.get('latest_file', 'none')}")
        else:
            logger.debug("No macro context found — running without macro intuition")

        for attempt in range(max_retries):
            client = self._get_gemini_client()
            if not client: return None

            try:
                # ── FIX: import types BEFORE if-images block (always needed for GenerateContentConfig)
                from google.genai import types

                # ── Prepare contents ───────────────────────────────────────
                contents = []
                if text:
                    contents.append(f"SIGNAL TEXT:\n{text}")

                # Load first image only for speed
                if images:
                    img_data = images[0]
                    if isinstance(img_data, str):
                        with open(img_data, "rb") as f:
                            img_bytes = f.read()
                    else:
                        img_bytes = img_data
                    contents.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))

                # ── Build Master Prompt with Macro Intuition ──────────────
                macro_section = (
                    f"{macro_prompt}\n\n"
                    if macro_prompt else
                    ""
                )

                prompt = (
                    f"{macro_section}"
                    "You are a Master Crypto Futures Trader with macro market wisdom.\n"
                    "Analyze the provided signal data (text and/or chart image) using:\n"
                    "  1. Smart Money Concepts (SMC): Order Blocks, Liquidity Grabs, Fair Value Gaps\n"
                    "  2. Technical Analysis: Support/Resistance, RSI, EMA, Volume\n"
                    "  3. Macro Alignment: Cross-check signal against the MACRO CONTEXT above\n\n"
                    "CRITICAL RULES:\n"
                    "  - Do NOT enter LONG on altcoins during confirmed bear market unless macro says otherwise\n"
                    "  - If macro is BEARISH and signal is LONG: reduce confidence below 0.6 or SKIP\n"
                    "  - If there is war/conflict news in macro: avoid all except GOLD pairs\n"
                    "  - Keep leverage MAX 10x during bear market (5x if macro is very negative)\n"
                    "  - Only A+ setups should pass — quality over quantity\n\n"
                    "Respond ONLY with a valid JSON object (no markdown, no extra text):\n"
                    "{\n"
                    '    "action": "LONG/SHORT/NEWS/SKIP",\n'
                    '    "pair": "BASE/USDT",\n'
                    '    "entry": float,\n'
                    '    "targets": [float, float, float],\n'
                    '    "stop_loss": float,\n'
                    '    "leverage": int,\n'
                    '    "confidence": 0.0-1.0,\n'
                    '    "macro_aligned": true/false,\n'
                    '    "reasoning": "Mention: chart pattern, SMC structure, macro alignment status"\n'
                    "}"
                )

                response = client.models.generate_content(
                    model=self.gemini_model,
                    contents=[prompt] + contents,
                    config=types.GenerateContentConfig(temperature=0.2)
                )

                result = self._extract_json(response.text)
                if result:
                    # ── Macro Safety Cap: Auto-limit leverage in bear market ──
                    if macro_prompt and result.get("leverage", 0) > 10:
                        original_lev = result["leverage"]
                        result["leverage"] = 10
                        existing_reasoning = str(result.get("reasoning", ""))
                        result["reasoning"] = (
                            existing_reasoning +
                            f" [MACRO CAP: leverage reduced from {original_lev}x to 10x — bear market active]"
                        )
                        logger.info(f"⚠️  Macro Safety Cap: leverage {original_lev}x → 10x")

                    # ── Log macro alignment ────────────────────────────────
                    macro_aligned = result.get("macro_aligned", True)
                    if not macro_aligned:
                        logger.warning(f"⚠️  Gemini: Signal NOT aligned with macro context! "
                                       f"action={result.get('action')}, "
                                       f"confidence={result.get('confidence')}")

                    if result.get("action") != "SKIP":
                        logger.info(f"✓ Gemini + Macro Analysis OK (Key {self.current_gemini_idx}) "
                                    f"| macro_aligned={macro_aligned}")
                    return result
                return result

            except Exception as e:
                err = str(e)
                if "429" in err or "quota" in err.lower() or "RESOURCE_EXHAUSTED" in err:
                    logger.warning(f"Gemini Key {self.current_gemini_idx} quota limit. Rotating...")
                    self.current_gemini_idx = (self.current_gemini_idx + 1) % len(self.gemini_keys)
                    if attempt == max_retries - 1:
                        logger.warning(f"⚠️ Semua key Gemini limit. Mengaktifkan cooldown {self._gemini_cooldown_duration}s")
                        self._gemini_cooldown_until = time.time() + self._gemini_cooldown_duration
                    continue
                elif "API_KEY_INVALID" in err or "INVALID_ARGUMENT" in err:
                    logger.warning(f"Gemini Key {self.current_gemini_idx} INVALID. Skipping to next...")
                    self.current_gemini_idx = (self.current_gemini_idx + 1) % len(self.gemini_keys)
                    continue
                else:
                    logger.error(f"Gemini error: {e}")
                    return None
        
        return None

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
        """Analyze signal text with Groq (with Key Rotation)."""
        if not self.groq_client: return self._keyword_based_analysis(text)

        # ── Cek Groq Cooldown ──
        if time.time() < self._groq_cooldown_until:
            remaining = int(self._groq_cooldown_until - time.time())
            logger.debug(f"Semua Groq key kena limit, cooldown {remaining}s. Fallback ke keyword analysis.")
            return self._keyword_based_analysis(text)

        # Cari key yang belum kena limit — skip key yang sudah di-blacklist
        keys_tried = 0
        start_idx = self.current_groq_idx
        for _round in range(len(self.groq_keys)):
            idx = (start_idx + _round) % len(self.groq_keys)
            if self._groq_key_errors.get(idx, 0) >= 3:
                # Key ini sudah gagal 3x, skip
                keys_tried += 1
                continue
            self.current_groq_idx = idx
            self._init_fallback_clients()
            break
        else:
            # Semua key sudah di-blacklist → cooldown 1 jam
            logger.warning(f"⚠️ Semua {len(self.groq_keys)} Groq key kena limit. Cooldown {self._groq_cooldown_duration}s")
            self._groq_cooldown_until = time.time() + self._groq_cooldown_duration
            self._groq_key_errors.clear()  # Reset after cooldown
            return self._keyword_based_analysis(text)

        max_retries = len(self.groq_keys)
        for attempt in range(max_retries):
            try:
                context = f"\nChart image context: {json.dumps(image_context)}" if image_context else ""
                prompt = (
                    "Extract trading signal details into JSON.\n"
                    f"Message: {text}\n{context}\n\n"
                    "JSON mandatory fields: action (LONG/SHORT/NEWS/SKIP), pair, entry, targets, stop_loss, leverage, confidence, reasoning."
                )

                response = self.groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.1
                )

                self._last_groq_call = time.time()
                return json.loads(response.choices[0].message.content)

            except Exception as e:
                err = str(e)
                if "429" in err or "rate_limit" in err.lower() or "quota" in err.lower():
                    # Mark this key as errored
                    self._groq_key_errors[self.current_groq_idx] = self._groq_key_errors.get(self.current_groq_idx, 0) + 1
                    logger.warning(f"Groq Key {self.current_groq_idx} hit limit (error #{self._groq_key_errors[self.current_groq_idx]}). Rotating...")

                    # Try next key
                    next_idx = (self.current_groq_idx + 1) % len(self.groq_keys)
                    if self._groq_key_errors.get(next_idx, 0) < 3:
                        self.current_groq_idx = next_idx
                        self._init_fallback_clients()
                        continue
                    else:
                        # All keys tried and failed → cooldown
                        logger.warning(f"⚠️ Semua Groq key limit terkena. Aktifkan cooldown {self._groq_cooldown_duration}s")
                        self._groq_cooldown_until = time.time() + self._groq_cooldown_duration
                        self._groq_key_errors.clear()
                        return self._keyword_based_analysis(text)
                else:
                    logger.error(f"Groq Error: {e}")
                    return self._keyword_based_analysis(text)
        return self._keyword_based_analysis(text)


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

    def _to_float(self, value) -> Optional[float]:
        """Safely convert AI-returned value to float.
        Handles: None, str (with $, commas), int, float, list (takes first element).
        Returns None if conversion fails.
        """
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, list):
            if value:
                return self._to_float(value[0])
            return None
        if isinstance(value, str):
            cleaned = re.sub(r'[^\d.]', '', value.replace(',', ''))
            try:
                return float(cleaned) if cleaned else None
            except ValueError:
                return None
        return None

    def _sanitize_targets(self, targets) -> list:
        """Convert a list of target prices to list of floats, filtering out bad values."""
        if not targets:
            return []
        if not isinstance(targets, list):
            v = self._to_float(targets)
            return [v] if v is not None else []
        result = []
        for t in targets:
            v = self._to_float(t)
            if v is not None and v > 0:
                result.append(v)
        return result

    def _combine_analyses(self, raw_text: str, text_analysis: Optional[Dict],
                          image_analysis: Optional[Dict], channel: str) -> Optional[Dict]:
        """Combine text and image analysis into a final signal."""

        if not text_analysis and not image_analysis:
            return self._basic_parse(raw_text, channel)

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

        if text_analysis:
            action = text_analysis.get("action", "SKIP")
            if action in ("LONG", "SHORT"):
                signal["side"] = action
            elif action == "NEWS":
                signal["is_news"] = True
                signal["news_sentiment"] = text_analysis.get("sentiment", "NEUTRAL")
                signal["news_info"] = text_analysis.get("key_info", "")

            signal["pair"] = text_analysis.get("pair")
            # Sanitize all numeric fields to prevent type errors
            signal["entry"] = self._to_float(text_analysis.get("entry"))
            signal["targets"] = self._sanitize_targets(text_analysis.get("targets", []))
            signal["stop_loss"] = self._to_float(text_analysis.get("stop_loss"))
            signal["leverage"] = self._to_float(text_analysis.get("leverage"))
            # BUG FIX #3: Confidence harus di-cap 0.0-1.0. AI terkadang return 700% dsb
            raw_conf = self._to_float(text_analysis.get("confidence")) or 0.5
            signal["confidence"] = max(0.0, min(1.0, raw_conf))
            # BUG FIX #4: reasoning bisa berupa dict jika AI return nested JSON
            # Ini menyebabkan 'dict += str' crash — selalu convert ke str
            raw_reasoning = text_analysis.get("reasoning", "")
            signal["reasoning"] = str(raw_reasoning) if raw_reasoning else ""

        if image_analysis:
            img_signal = image_analysis.get("signal", "NEUTRAL")
            img_confidence = self._to_float(image_analysis.get("confidence")) or 0.5

            if not signal["pair"] and image_analysis.get("pair"):
                signal["pair"] = image_analysis["pair"]

            if signal["side"] and img_signal:
                text_dir = signal["side"]
                img_dir = img_signal
                if text_dir == img_dir:
                    signal["confidence"] = min(0.95, float(signal["confidence"]) * 1.2)
                    signal["reasoning"] = str(signal.get("reasoning", "")) + " | Chart confirms direction"
                elif img_dir == "NEUTRAL":
                    pass
                else:
                    signal["confidence"] = float(signal["confidence"]) * 0.6
                    signal["reasoning"] = str(signal.get("reasoning", "")) + f" | Chart shows {img_dir} (conflicts)"

            if not signal["side"] and img_signal in ("LONG", "SHORT"):
                signal["side"] = img_signal
                signal["confidence"] = img_confidence * 0.8

            if not signal["targets"] and image_analysis.get("targets"):
                signal["targets"] = self._sanitize_targets(image_analysis["targets"])
            if not signal["stop_loss"] and image_analysis.get("stop_loss"):
                signal["stop_loss"] = self._to_float(image_analysis["stop_loss"])
            if not signal["entry"] and image_analysis.get("entry_zone"):
                signal["entry"] = self._to_float(image_analysis["entry_zone"])

            signal["chart_pattern"] = image_analysis.get("pattern")
            signal["chart_summary"] = image_analysis.get("summary")

        if not signal.get("side") or not signal.get("pair"):
            if signal.get("is_news"):
                return signal
            return None

        pair = signal["pair"]
        if pair:
            pair = str(pair).upper().replace(" ", "")
            if "/" not in pair:
                pair = pair.replace("USDT", "/USDT")
            if not pair.endswith("/USDT"):
                pair = pair + "/USDT"
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

        max_retries = len(self.groq_keys)
        for attempt in range(max_retries):
            try:
                # ── Cek Cooldown Groq ──
                if hasattr(self, "_groq_cooldown_until") and time.time() < self._groq_cooldown_until:
                    remaining = int(self._groq_cooldown_until - time.time())
                    logger.debug(f"Groq sedang dalam cooldown ({remaining}s tersisa). Lewati text analysis.")
                    break

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
                err = str(e)
                if "429" in err and len(self.groq_keys) > 1:
                    logger.warning(f"Groq Key {self.current_groq_idx} limit hit di news context. Rotating...")
                    self.current_groq_idx = (self.current_groq_idx + 1) % len(self.groq_keys)
                    self._init_fallback_clients()
                    if attempt == max_retries - 1:
                        logger.warning("⚠️ Semua key Groq limit. Mengaktifkan cooldown 120s")
                        self._groq_cooldown_until = time.time() + 120
                    continue
                else:
                    logger.error(f"News analysis error: {e}")
                    break

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
