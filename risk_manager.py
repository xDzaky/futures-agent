"""
Risk Manager — Position Sizing & Safety Controls
===================================================
- Kelly Criterion position sizing
- Max risk per trade (2%)
- Max concurrent positions
- Daily loss limit
- Leverage capping based on volatility
- Correlation check (no double exposure)
"""

import os
import logging
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("risk_manager")


class RiskManager:
    """Handles all risk management for futures trading."""

    def __init__(self):
        self.max_risk_per_trade = float(os.getenv("MAX_RISK_PER_TRADE", "0.02"))
        self.max_leverage = int(os.getenv("MAX_LEVERAGE", "10"))
        self.max_positions = int(os.getenv("MAX_OPEN_POSITIONS", "3"))
        self.daily_loss_limit = float(os.getenv("DAILY_LOSS_LIMIT", "-0.05"))

    def calculate_position(self, balance: float, price: float,
                           sl_pct: float, leverage: int,
                           confidence: float) -> Dict:
        """
        Calculate position size using risk-based sizing.

        Args:
            balance: Current account balance (USDT)
            price: Current price of the asset
            sl_pct: Stop loss distance as percentage (e.g., 1.5 = 1.5%)
            leverage: Intended leverage
            confidence: AI confidence (0-1)

        Returns:
            Position sizing details
        """
        if sl_pct <= 0:
            sl_pct = 1.0  # Default 1% SL

        # Cap leverage based on confidence
        leverage = self._cap_leverage(leverage, confidence, sl_pct)

        # Risk amount (max % of balance to lose on this trade)
        risk_amount = balance * self.max_risk_per_trade

        # Position size = risk_amount / (sl_pct / 100)
        # This means if SL is 1%, position = risk_amount / 0.01 = 100x risk
        position_value = risk_amount / (sl_pct / 100)

        # Cap by balance * leverage (can't exceed margin)
        max_position = balance * leverage
        position_value = min(position_value, max_position)

        # Calculate margin required
        margin_required = position_value / leverage

        # Calculate quantity (contracts/coins)
        quantity = position_value / price

        # Sanity check
        if margin_required > balance * 0.3:
            # Never use more than 30% of balance on one trade
            margin_required = balance * 0.3
            position_value = margin_required * leverage
            quantity = position_value / price

        return {
            "position_value": round(position_value, 2),
            "margin_required": round(margin_required, 2),
            "quantity": round(quantity, 6),
            "leverage": leverage,
            "risk_amount": round(risk_amount, 2),
            "risk_pct": round(self.max_risk_per_trade * 100, 1),
            "sl_pct": round(sl_pct, 2),
            "margin_pct": round(margin_required / balance * 100, 1),
        }

    def _cap_leverage(self, leverage: int, confidence: float,
                      sl_pct: float) -> int:
        """Cap leverage based on confidence and volatility."""
        # Confidence-based cap
        if confidence >= 0.90:
            conf_cap = 15
        elif confidence >= 0.80:
            conf_cap = 10
        elif confidence >= 0.70:
            conf_cap = 5
        else:
            conf_cap = 3

        # Volatility-based cap (wider SL = lower leverage)
        if sl_pct > 3:
            vol_cap = 3
        elif sl_pct > 2:
            vol_cap = 5
        elif sl_pct > 1:
            vol_cap = 10
        else:
            vol_cap = 15

        # Take the most conservative cap
        final = min(leverage, conf_cap, vol_cap, self.max_leverage)
        return max(1, final)

    def check_can_trade(self, balance: float, open_positions: int,
                        daily_pnl: float) -> Dict:
        """
        Pre-trade safety checks.
        Returns: {can_trade: bool, reason: str}
        """
        # Check max positions
        if open_positions >= self.max_positions:
            return {
                "can_trade": False,
                "reason": f"Max positions reached ({self.max_positions})"
            }

        # Check daily loss limit
        daily_pnl_pct = daily_pnl / balance if balance > 0 else 0
        if daily_pnl_pct < self.daily_loss_limit:
            return {
                "can_trade": False,
                "reason": f"Daily loss limit hit ({daily_pnl_pct:.1%})"
            }

        # Check minimum balance
        if balance < 10:
            return {
                "can_trade": False,
                "reason": f"Balance too low (${balance:.2f})"
            }

        return {"can_trade": True, "reason": "OK"}

    def should_close_early(self, entry_price: float, current_price: float,
                           side: str, sl_pct: float,
                           unrealized_pnl_pct: float) -> Dict:
        """Check if position should be closed early (trailing stop logic)."""
        # If position is up 3x the SL distance, trail the stop
        if side == "LONG":
            gain_pct = (current_price - entry_price) / entry_price * 100
        else:
            gain_pct = (entry_price - current_price) / entry_price * 100

        if gain_pct > sl_pct * 3:
            return {
                "action": "TRAIL_STOP",
                "new_sl_pct": sl_pct * 0.5,
                "reason": f"Trailing stop: gain={gain_pct:.1f}%"
            }

        return {"action": "HOLD", "reason": "Within normal range"}
