"""
Exchange Connector — Binance Futures (Testnet + Live)
======================================================
Uses ccxt for unified exchange API. Supports:
- Binance Futures Testnet (paper trading)
- Binance Futures Live (real money)
- Easy to switch to Bybit, Bitunix, etc.
"""

import os
import ccxt
import logging
import time
from typing import Optional, Dict, List
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("exchange")


class FuturesExchange:
    """Unified futures exchange connector via ccxt."""

    def __init__(self):
        self.use_testnet = os.getenv("USE_TESTNET", "true").lower() == "true"
        api_key = os.getenv("BINANCE_TESTNET_KEY", "")
        api_secret = os.getenv("BINANCE_TESTNET_SECRET", "")

        self.exchange = ccxt.binance({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
            },
        })

        if self.use_testnet:
            self.exchange.set_sandbox_mode(True)
            logger.info("Exchange: Binance Futures TESTNET")
        else:
            logger.info("Exchange: Binance Futures LIVE")

        self._markets_loaded = False

    def _ensure_markets(self):
        if not self._markets_loaded:
            self.exchange.load_markets()
            self._markets_loaded = True

    # ─── Market Data ──────────────────────────────

    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """Get current ticker for a symbol (e.g., BTC/USDT)."""
        try:
            self._ensure_markets()
            return self.exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.error(f"Ticker error {symbol}: {e}")
            return None

    def get_all_tickers(self) -> Dict:
        """Get tickers for all futures pairs."""
        try:
            self._ensure_markets()
            return self.exchange.fetch_tickers()
        except Exception as e:
            logger.error(f"All tickers error: {e}")
            return {}

    def get_ohlcv(self, symbol: str, timeframe: str = "5m",
                  limit: int = 100) -> List:
        """Get OHLCV candle data."""
        try:
            self._ensure_markets()
            return self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        except Exception as e:
            logger.error(f"OHLCV error {symbol} {timeframe}: {e}")
            return []

    def get_orderbook(self, symbol: str, limit: int = 20) -> Optional[Dict]:
        """Get order book (bids/asks)."""
        try:
            self._ensure_markets()
            return self.exchange.fetch_order_book(symbol, limit)
        except Exception as e:
            logger.error(f"Orderbook error {symbol}: {e}")
            return None

    def get_funding_rate(self, symbol: str) -> Optional[Dict]:
        """Get current funding rate."""
        try:
            self._ensure_markets()
            rates = self.exchange.fetch_funding_rate(symbol)
            return rates
        except Exception as e:
            logger.debug(f"Funding rate error {symbol}: {e}")
            return None

    # ─── Account ──────────────────────────────────

    def get_balance(self) -> Dict:
        """Get account balance."""
        try:
            self._ensure_markets()
            balance = self.exchange.fetch_balance()
            usdt = balance.get("USDT", {})
            return {
                "total": usdt.get("total", 0),
                "free": usdt.get("free", 0),
                "used": usdt.get("used", 0),
            }
        except Exception as e:
            logger.error(f"Balance error: {e}")
            return {"total": 0, "free": 0, "used": 0}

    def get_positions(self) -> List[Dict]:
        """Get all open positions."""
        try:
            self._ensure_markets()
            positions = self.exchange.fetch_positions()
            return [p for p in positions
                    if float(p.get("contracts", 0)) > 0]
        except Exception as e:
            logger.error(f"Positions error: {e}")
            return []

    # ─── Orders ───────────────────────────────────

    def set_leverage(self, symbol: str, leverage: int):
        """Set leverage for a symbol."""
        try:
            self._ensure_markets()
            self.exchange.set_leverage(leverage, symbol)
            logger.info(f"Leverage set: {symbol} = {leverage}x")
        except Exception as e:
            logger.debug(f"Set leverage error {symbol}: {e}")

    def set_margin_mode(self, symbol: str, mode: str = "isolated"):
        """Set margin mode (isolated/cross)."""
        try:
            self._ensure_markets()
            self.exchange.set_margin_mode(mode, symbol)
        except Exception as e:
            logger.debug(f"Margin mode error {symbol}: {e}")

    def open_long(self, symbol: str, amount: float,
                  leverage: int = 5,
                  stop_loss: float = None,
                  take_profit: float = None) -> Optional[Dict]:
        """Open a LONG position."""
        try:
            self._ensure_markets()
            self.set_leverage(symbol, leverage)
            self.set_margin_mode(symbol, "isolated")

            # Market buy
            order = self.exchange.create_market_buy_order(
                symbol, amount
            )

            # Set SL/TP
            if stop_loss:
                self._set_stop_loss(symbol, "sell", amount, stop_loss)
            if take_profit:
                self._set_take_profit(symbol, "sell", amount, take_profit)

            logger.info(f"LONG {symbol}: {amount} @ {leverage}x")
            return order
        except Exception as e:
            logger.error(f"Long order error {symbol}: {e}")
            return None

    def open_short(self, symbol: str, amount: float,
                   leverage: int = 5,
                   stop_loss: float = None,
                   take_profit: float = None) -> Optional[Dict]:
        """Open a SHORT position."""
        try:
            self._ensure_markets()
            self.set_leverage(symbol, leverage)
            self.set_margin_mode(symbol, "isolated")

            # Market sell
            order = self.exchange.create_market_sell_order(
                symbol, amount
            )

            # Set SL/TP
            if stop_loss:
                self._set_stop_loss(symbol, "buy", amount, stop_loss)
            if take_profit:
                self._set_take_profit(symbol, "buy", amount, take_profit)

            logger.info(f"SHORT {symbol}: {amount} @ {leverage}x")
            return order
        except Exception as e:
            logger.error(f"Short order error {symbol}: {e}")
            return None

    def close_position(self, symbol: str, side: str,
                       amount: float) -> Optional[Dict]:
        """Close a position."""
        try:
            self._ensure_markets()
            if side == "long":
                order = self.exchange.create_market_sell_order(symbol, amount)
            else:
                order = self.exchange.create_market_buy_order(symbol, amount)
            logger.info(f"CLOSED {side} {symbol}: {amount}")
            return order
        except Exception as e:
            logger.error(f"Close error {symbol}: {e}")
            return None

    def _set_stop_loss(self, symbol: str, side: str,
                       amount: float, price: float):
        """Set stop-loss order."""
        try:
            params = {"stopPrice": price, "reduceOnly": True}
            self.exchange.create_order(
                symbol, "stop_market", side, amount, None, params
            )
        except Exception as e:
            logger.debug(f"SL error: {e}")

    def _set_take_profit(self, symbol: str, side: str,
                         amount: float, price: float):
        """Set take-profit order."""
        try:
            params = {"stopPrice": price, "reduceOnly": True}
            self.exchange.create_order(
                symbol, "take_profit_market", side, amount, None, params
            )
        except Exception as e:
            logger.debug(f"TP error: {e}")

    def cancel_all_orders(self, symbol: str):
        """Cancel all open orders for a symbol."""
        try:
            self._ensure_markets()
            self.exchange.cancel_all_orders(symbol)
        except Exception as e:
            logger.debug(f"Cancel orders error {symbol}: {e}")

    # ─── Market Info ──────────────────────────────

    def get_market_info(self, symbol: str) -> Optional[Dict]:
        """Get market specs (min order, tick size, etc.)."""
        try:
            self._ensure_markets()
            market = self.exchange.market(symbol)
            return {
                "symbol": symbol,
                "min_amount": market.get("limits", {}).get("amount", {}).get("min", 0),
                "min_cost": market.get("limits", {}).get("cost", {}).get("min", 0),
                "price_precision": market.get("precision", {}).get("price", 2),
                "amount_precision": market.get("precision", {}).get("amount", 3),
                "maker_fee": market.get("maker", 0.0002),
                "taker_fee": market.get("taker", 0.0004),
            }
        except Exception as e:
            logger.error(f"Market info error {symbol}: {e}")
            return None

    def get_available_pairs(self) -> List[str]:
        """Get all available USDT futures pairs."""
        try:
            self._ensure_markets()
            return [s for s in self.exchange.symbols
                    if s.endswith("/USDT") and ":USDT" in s]
        except Exception as e:
            logger.error(f"Get pairs error: {e}")
            return []
