"""
Trade Database — SQLite Tracking for Futures Agent
=====================================================
Tracks all trades, P&L, balance history.
Similar to Polymarket agent but adapted for futures.
"""

import os
import sqlite3
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger("trade_db")

DB_PATH = os.path.join(os.path.dirname(__file__), "futures_trades.db")


class TradeDB:
    """SQLite database for trading history and performance tracking."""

    def __init__(self, db_path: str = DB_PATH,
                 starting_balance: float = 1000.0):
        self.db_path = db_path
        self.starting_balance = starting_balance
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    action TEXT NOT NULL,
                    entry_price REAL,
                    exit_price REAL,
                    quantity REAL,
                    leverage INTEGER DEFAULT 1,
                    margin REAL,
                    position_value REAL,
                    stop_loss REAL,
                    tp1 REAL,
                    tp2 REAL,
                    tp3 REAL,
                    sl_pct REAL,
                    confidence REAL,
                    ai_reasoning TEXT,
                    model TEXT,
                    ta_score REAL,
                    status TEXT DEFAULT 'OPEN',
                    profit REAL DEFAULT 0,
                    profit_pct REAL DEFAULT 0,
                    fee REAL DEFAULT 0,
                    opened_at TEXT,
                    closed_at TEXT,
                    hold_duration TEXT,
                    close_reason TEXT,
                    cycle INTEGER DEFAULT 0
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS balance_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    balance REAL,
                    pnl REAL,
                    event TEXT,
                    cycle INTEGER DEFAULT 0
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # Initialize state
            cursor = conn.execute(
                "SELECT value FROM agent_state WHERE key = 'balance'"
            )
            if not cursor.fetchone():
                conn.execute(
                    "INSERT INTO agent_state (key, value) VALUES (?, ?)",
                    ("balance", str(self.starting_balance))
                )
                conn.execute(
                    "INSERT INTO agent_state (key, value) VALUES (?, ?)",
                    ("total_pnl", "0.0")
                )
                conn.execute(
                    "INSERT INTO agent_state (key, value) VALUES (?, ?)",
                    ("daily_pnl", "0.0")
                )
                conn.execute(
                    "INSERT INTO agent_state (key, value) VALUES (?, ?)",
                    ("daily_date", datetime.now().strftime("%Y-%m-%d"))
                )
                conn.execute(
                    "INSERT INTO balance_history (timestamp, balance, pnl, event, cycle) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (datetime.now().isoformat(), self.starting_balance, 0, "INIT", 0)
                )
                conn.commit()

    # ─── State ────────────────────────────────────

    def _get(self, key: str, default: str = "0.0") -> str:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT value FROM agent_state WHERE key = ?", (key,)
            )
            row = cur.fetchone()
            return row[0] if row else default

    def _set(self, key: str, value: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO agent_state (key, value) VALUES (?, ?)",
                (key, value)
            )
            conn.commit()

    @property
    def balance(self) -> float:
        return float(self._get("balance", str(self.starting_balance)))

    @balance.setter
    def balance(self, v: float):
        self._set("balance", str(round(v, 4)))

    @property
    def total_pnl(self) -> float:
        return float(self._get("total_pnl", "0.0"))

    @total_pnl.setter
    def total_pnl(self, v: float):
        self._set("total_pnl", str(round(v, 4)))

    @property
    def daily_pnl(self) -> float:
        # Reset daily PNL if new day
        stored_date = self._get("daily_date", "")
        today = datetime.now().strftime("%Y-%m-%d")
        if stored_date != today:
            self._set("daily_pnl", "0.0")
            self._set("daily_date", today)
            return 0.0
        return float(self._get("daily_pnl", "0.0"))

    @daily_pnl.setter
    def daily_pnl(self, v: float):
        self._set("daily_pnl", str(round(v, 4)))
        self._set("daily_date", datetime.now().strftime("%Y-%m-%d"))

    # ─── Trade Operations ─────────────────────────

    def open_trade(self, signal: Dict, cycle: int = 0) -> Dict:
        """Record a new trade opening."""
        now = datetime.now().isoformat()

        # Deduct margin from balance
        margin = signal.get("margin", 0)
        fee = signal.get("position_value", 0) * 0.0004  # 0.04% taker fee
        self.balance -= (margin + fee)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO trades (
                    symbol, side, action, entry_price, quantity, leverage,
                    margin, position_value, stop_loss, tp1, tp2, tp3,
                    sl_pct, confidence, ai_reasoning, model, ta_score,
                    status, fee, opened_at, cycle
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal.get("symbol"),
                signal.get("side"),
                signal.get("action"),
                signal.get("entry_price"),
                signal.get("quantity"),
                signal.get("leverage"),
                margin,
                signal.get("position_value"),
                signal.get("stop_loss"),
                signal.get("tp1"),
                signal.get("tp2"),
                signal.get("tp3"),
                signal.get("sl_pct"),
                signal.get("confidence"),
                signal.get("reasoning", ""),
                signal.get("model", ""),
                signal.get("ta_score", 0),
                "OPEN",
                round(fee, 4),
                now,
                cycle,
            ))
            trade_id = cursor.lastrowid

            conn.execute(
                "INSERT INTO balance_history (timestamp, balance, pnl, event, cycle) "
                "VALUES (?, ?, ?, ?, ?)",
                (now, self.balance, -(margin + fee), f"OPEN #{trade_id}", cycle)
            )
            conn.commit()

        return {"id": trade_id, "fee": round(fee, 4), "margin": margin}

    def close_trade(self, trade_id: int, exit_price: float,
                    reason: str = "MANUAL", cycle: int = 0) -> Dict:
        """Close a trade and calculate P&L."""
        trade = self.get_trade(trade_id)
        if not trade:
            return {"error": "Trade not found"}

        entry = trade["entry_price"]
        side = trade["side"]
        qty = trade["quantity"]
        leverage = trade["leverage"]
        margin = trade["margin"]

        # Calculate P&L
        if side == "LONG":
            pnl_pct = (exit_price - entry) / entry * 100
        else:
            pnl_pct = (entry - exit_price) / entry * 100

        profit = margin * (pnl_pct / 100) * leverage
        exit_fee = trade["position_value"] * 0.0004

        net_profit = profit - exit_fee

        # Update balance
        self.balance += (margin + net_profit)
        self.total_pnl += net_profit
        self.daily_pnl = self.daily_pnl + net_profit

        # Hold duration
        try:
            opened = datetime.fromisoformat(trade["opened_at"])
            duration = str(datetime.now() - opened).split(".")[0]
        except Exception:
            duration = "unknown"

        now = datetime.now().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE trades SET
                    exit_price = ?, profit = ?, profit_pct = ?,
                    fee = fee + ?, status = ?, closed_at = ?,
                    hold_duration = ?, close_reason = ?
                WHERE id = ?
            """, (
                exit_price, round(net_profit, 4), round(pnl_pct, 2),
                exit_fee,
                "WIN" if net_profit > 0 else "LOSS",
                now, duration, reason, trade_id,
            ))

            conn.execute(
                "INSERT INTO balance_history (timestamp, balance, pnl, event, cycle) "
                "VALUES (?, ?, ?, ?, ?)",
                (now, self.balance, net_profit, f"CLOSE #{trade_id} {reason}", cycle)
            )
            conn.commit()

        return {
            "id": trade_id,
            "symbol": trade["symbol"],
            "side": side,
            "entry": entry,
            "exit": exit_price,
            "profit": round(net_profit, 2),
            "profit_pct": round(pnl_pct, 2),
            "duration": duration,
            "reason": reason,
            "balance": round(self.balance, 2),
        }

    # ─── Queries ──────────────────────────────────

    def get_trade(self, trade_id: int) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_open_trades(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM trades WHERE status = 'OPEN' ORDER BY opened_at DESC"
            )
            return [dict(row) for row in cur.fetchall()]

    def get_closed_trades(self, limit: int = 20) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM trades WHERE status != 'OPEN' "
                "ORDER BY closed_at DESC LIMIT ?", (limit,)
            )
            return [dict(row) for row in cur.fetchall()]

    def get_stats(self) -> Dict:
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
            wins = conn.execute(
                "SELECT COUNT(*) FROM trades WHERE status = 'WIN'"
            ).fetchone()[0]
            losses = conn.execute(
                "SELECT COUNT(*) FROM trades WHERE status = 'LOSS'"
            ).fetchone()[0]
            open_count = conn.execute(
                "SELECT COUNT(*) FROM trades WHERE status = 'OPEN'"
            ).fetchone()[0]
            total_fees = conn.execute(
                "SELECT COALESCE(SUM(fee), 0) FROM trades"
            ).fetchone()[0]

        win_rate = (wins / max(1, wins + losses)) * 100
        roi = ((self.balance - self.starting_balance) /
               self.starting_balance * 100)

        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "open_positions": open_count,
            "win_rate": round(win_rate, 1),
            "balance": round(self.balance, 2),
            "total_pnl": round(self.total_pnl, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "total_fees": round(total_fees, 4),
            "roi": round(roi, 2),
            "starting_balance": self.starting_balance,
        }

    def is_symbol_open(self, symbol: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM trades WHERE symbol = ? AND status = 'OPEN'",
                (symbol,)
            ).fetchone()[0]
            return count > 0

    def update_stop_loss(self, trade_id: int, new_sl: float):
        """Update stop loss for an open trade (trailing stop)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE trades SET stop_loss = ? WHERE id = ? AND status = 'OPEN'",
                (round(new_sl, 6), trade_id)
            )
            conn.commit()
        logger.debug(f"Updated SL for trade #{trade_id} to {new_sl}")

