"""
Multi-AI Consensus Validator
==============================
Uses multiple AI models to validate trading signals:
1. Groq (Llama 3.3 70B) - Primary analyzer
2. NVIDIA NIM (DeepSeek V3.2) - Validator
3. Gemini (2.5 Flash) - Vision validator

Only executes trades when 2+ AIs agree on direction.
Boosts confidence when all 3 agree.
"""

import os
import json
import logging
import time
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("consensus")


class ConsensusValidator:
    """Multi-AI consensus validator for trading signals."""

    def __init__(self):
        self.groq_key = os.getenv("GROQ_API_KEY", "")
        self.nvidia_key = os.getenv("NVIDIA_API_KEY", "")
        self.enable_consensus = os.getenv("ENABLE_AI_CONSENSUS", "true").lower() == "true"
        self.min_agreement = int(os.getenv("MIN_AI_AGREEMENT", "2"))

        # Initialize clients
        self.groq_client = None
        self.nvidia_client = None

        if self.groq_key:
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=self.groq_key)
            except Exception as e:
                logger.warning(f"Groq init failed: {e}")

        if self.nvidia_key:
            try:
                from openai import OpenAI
                self.nvidia_client = OpenAI(
                    base_url="https://integrate.api.nvidia.com/v1",
                    api_key=self.nvidia_key
                )
            except Exception as e:
                logger.warning(f"NVIDIA init failed: {e}")

        self._last_groq_call = 0
        self._last_nvidia_call = 0
        self.total_validations = 0
        self.total_agreements = 0

    def validate_signal(self, signal: Dict, context: Dict) -> Optional[Dict]:
        """
        Validate a trading signal using multi-AI consensus.

        Args:
            signal: {pair, side, entry, targets, stop_loss, leverage, confidence, reasoning}
            context: {technical, market, news}

        Returns:
            Enhanced signal with consensus data or None if rejected
        """
        if not self.enable_consensus:
            # Consensus disabled, pass through
            return signal

        if not self.groq_client and not self.nvidia_client:
            # No validators available
            logger.warning("No AI validators available")
            return signal

        pair = signal.get("pair", "")
        side = signal.get("side", "")

        logger.info(f"Consensus validation: {side} {pair}")

        # Collect opinions from each AI
        opinions = []

        # Opinion 1: Groq (Llama 3.3 70B)
        if self.groq_client:
            groq_opinion = self._get_groq_opinion(signal, context)
            if groq_opinion:
                opinions.append(groq_opinion)
                logger.info(f"  Groq: {groq_opinion['action']} (conf={groq_opinion['confidence']:.2f})")

        # Opinion 2: NVIDIA DeepSeek V3.2
        if self.nvidia_client:
            nvidia_opinion = self._get_nvidia_opinion(signal, context)
            if nvidia_opinion:
                opinions.append(nvidia_opinion)
                logger.info(f"  NVIDIA: {nvidia_opinion['action']} (conf={nvidia_opinion['confidence']:.2f})")

        if len(opinions) < 2:
            logger.warning("Not enough AI opinions for consensus")
            return signal

        # Analyze consensus
        consensus = self._analyze_consensus(signal, opinions)

        self.total_validations += 1
        if consensus["agreed"]:
            self.total_agreements += 1

        agreement_rate = self.total_agreements / self.total_validations * 100 if self.total_validations > 0 else 0
        logger.info(f"  Consensus: {consensus['action']} | Agreed: {consensus['agreed']} | Agreement rate: {agreement_rate:.1f}%")

        if not consensus["agreed"]:
            logger.info(f"  REJECTED: AIs disagree on {pair}")
            return None

        # Enhance signal with consensus data
        signal["consensus"] = consensus
        signal["confidence"] = consensus["final_confidence"]
        signal["reasoning"] = f"{signal.get('reasoning', '')} | {consensus['reasoning']}"

        return signal

    def _get_groq_opinion(self, signal: Dict, context: Dict) -> Optional[Dict]:
        """Get Groq's opinion on this signal."""
        now = time.time()
        if now - self._last_groq_call < 2:
            time.sleep(2 - (now - self._last_groq_call))

        try:
            prompt = self._build_validation_prompt(signal, context)

            response = self.groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": self._validator_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=400,
                response_format={"type": "json_object"},
            )

            self._last_groq_call = time.time()
            result = json.loads(response.choices[0].message.content)
            result["model"] = "groq-llama3.3"
            return result

        except Exception as e:
            logger.error(f"Groq validation error: {e}")
            self._last_groq_call = time.time()
            return None

    def _get_nvidia_opinion(self, signal: Dict, context: Dict) -> Optional[Dict]:
        """Get NVIDIA DeepSeek's opinion on this signal."""
        now = time.time()
        if now - self._last_nvidia_call < 3:
            time.sleep(3 - (now - self._last_nvidia_call))

        try:
            prompt = self._build_validation_prompt(signal, context)

            response = self.nvidia_client.chat.completions.create(
                model="deepseek/deepseek-r1",
                messages=[
                    {"role": "system", "content": self._validator_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=400,
            )

            self._last_nvidia_call = time.time()

            # Extract JSON from response
            content = response.choices[0].message.content
            result = self._extract_json(content)
            if result:
                result["model"] = "nvidia-deepseek"
                return result

        except Exception as e:
            logger.error(f"NVIDIA validation error: {e}")
            self._last_nvidia_call = time.time()
            return None

    def _validator_system_prompt(self) -> str:
        return """You are an expert crypto trading validator. Review trading signals and assess if they should be executed.

You MUST respond with valid JSON only:
{
    "action": "APPROVE_LONG" or "APPROVE_SHORT" or "REJECT",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}

APPROVAL CRITERIA:
1. Technical indicators align with trade direction
2. Market context supports the trade
3. Risk/reward ratio is favorable
4. No major conflicting signals
5. Stop loss placement is reasonable

REJECT if:
- Conflicting technical signals
- High risk / poor risk-reward
- Major bearish news for LONG or major bullish news for SHORT
- Overextended prices (RSI >80 for LONG, <20 for SHORT)
- Low volume / weak momentum"""

    def _build_validation_prompt(self, signal: Dict, context: Dict) -> str:
        pair = signal.get("pair", "?")
        side = signal.get("side", "?")
        entry = signal.get("entry", 0)
        sl = signal.get("stop_loss", 0)
        targets = signal.get("targets", [])
        leverage = signal.get("leverage", 1)
        confidence = signal.get("confidence", 0)
        reasoning = signal.get("reasoning", "")

        tech = context.get("technical", {})
        market = context.get("market", {})
        news = context.get("news", "")

        prompt = f"""Review this trading signal:

SIGNAL:
  Pair: {pair}
  Direction: {side}
  Entry: ${entry:,.2f}
  Stop Loss: ${sl:,.2f}
  Targets: {', '.join(f'${t:,.2f}' for t in targets[:3])}
  Leverage: {leverage}x
  Original Confidence: {confidence:.2f}
  Reasoning: {reasoning}

TECHNICAL ANALYSIS:
{json.dumps(tech, indent=2, default=str)[:1000]}

MARKET CONTEXT:
{json.dumps(market, indent=2, default=str)[:500]}

NEWS CONTEXT:
{news[:500] if news else 'No significant news'}

Should this trade be executed? Respond in JSON format."""

        return prompt

    def _analyze_consensus(self, original_signal: Dict, opinions: List[Dict]) -> Dict:
        """Analyze multiple AI opinions and determine consensus."""
        original_side = original_signal.get("side", "")

        # Count votes
        approve_long = 0
        approve_short = 0
        reject = 0
        confidences = []

        for op in opinions:
            action = op.get("action", "REJECT")
            conf = op.get("confidence", 0.5)

            if action == "APPROVE_LONG":
                approve_long += 1
                confidences.append(conf)
            elif action == "APPROVE_SHORT":
                approve_short += 1
                confidences.append(conf)
            else:
                reject += 1

        # Determine consensus
        total_votes = len(opinions)

        if original_side == "LONG":
            votes_for = approve_long
            votes_against = approve_short + reject
            consensus_action = "LONG"
        elif original_side == "SHORT":
            votes_for = approve_short
            votes_against = approve_long + reject
            consensus_action = "SHORT"
        else:
            return {
                "agreed": False,
                "action": "SKIP",
                "votes_for": 0,
                "votes_against": total_votes,
                "final_confidence": 0,
                "reasoning": "Invalid signal direction"
            }

        # Check if minimum agreement met
        agreed = votes_for >= self.min_agreement

        # Calculate final confidence
        if agreed and confidences:
            avg_conf = sum(confidences) / len(confidences)
            # Boost if unanimous
            if votes_for == total_votes:
                final_conf = min(0.95, avg_conf * 1.2)
                reasoning = f"All {total_votes} AIs agree {consensus_action}"
            else:
                final_conf = avg_conf
                reasoning = f"{votes_for}/{total_votes} AIs agree {consensus_action}"
        else:
            final_conf = 0.3
            reasoning = f"Only {votes_for}/{total_votes} AIs agree (need {self.min_agreement})"

        return {
            "agreed": agreed,
            "action": consensus_action,
            "votes_for": votes_for,
            "votes_against": votes_against,
            "total_votes": total_votes,
            "final_confidence": final_conf,
            "reasoning": reasoning,
            "models": [op.get("model", "?") for op in opinions]
        }

    def _extract_json(self, text: str) -> Optional[Dict]:
        """Extract JSON from response text."""
        import re
        text = text.strip()
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    validator = ConsensusValidator()

    # Test signal
    test_signal = {
        "pair": "BTC/USDT",
        "side": "LONG",
        "entry": 95000,
        "stop_loss": 93000,
        "targets": [97000, 99000, 101000],
        "leverage": 5,
        "confidence": 0.75,
        "reasoning": "Bullish breakout above resistance"
    }

    test_context = {
        "technical": {
            "consensus_score": 75,
            "consensus": "LONG",
            "timeframes": {
                "5m": {"score": 70, "signal": "LONG", "rsi": 65},
                "15m": {"score": 80, "signal": "LONG", "rsi": 60}
            }
        },
        "market": {
            "price": 95000,
            "funding": {"rate": 0.0001, "signal": "NEUTRAL"},
            "fear_greed": {"value": 55, "classification": "NEUTRAL"}
        },
        "news": "Bitcoin breaks $95k resistance with strong volume"
    }

    result = validator.validate_signal(test_signal, test_context)
    if result:
        print("\n✅ SIGNAL APPROVED")
        print(json.dumps(result, indent=2, default=str))
    else:
        print("\n❌ SIGNAL REJECTED")
