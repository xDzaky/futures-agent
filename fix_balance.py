"""
Fix Balance Script
==================
The old code had a bug: it deducted margin + fee from balance when OPENING a trade.
In paper trading, balance should only change when a trade CLOSES (realized P&L).

This script corrects the balance in realtime_trades.db back to $50.00
(or adjusts by the margin that was wrongly deducted).

Run ONCE with the bot STOPPED, then restart the bot.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "realtime_trades.db")

def fix_balance():
    if not os.path.exists(DB_PATH):
        print(f"Database not found: {DB_PATH}")
        return

    with sqlite3.connect(DB_PATH) as conn:
        # Get current balance
        row = conn.execute("SELECT value FROM agent_state WHERE key = 'balance'").fetchone()
        current_balance = float(row[0]) if row else 0.0
        print(f"Current (wrong) balance: ${current_balance:.4f}")

        # Get total margin + fees wrongly deducted from open trades
        open_trades = conn.execute(
            "SELECT id, symbol, side, margin, position_value, fee FROM trades WHERE status = 'OPEN'"
        ).fetchall()

        total_wrongly_deducted = 0.0
        print(f"\nOpen trades ({len(open_trades)}):")
        for t in open_trades:
            trade_id, symbol, side, margin, pos_val, fee = t
            # Fee was position_value * 0.0004 computed at open time
            fee_at_open = (pos_val or 0) * 0.0004
            wrongly_deducted = margin + fee_at_open
            total_wrongly_deducted += wrongly_deducted
            print(f"  #{trade_id} {side} {symbol}: margin=${margin:.2f} | fee_open=${fee_at_open:.4f} | wrongly_deducted=${wrongly_deducted:.4f}")

        corrected_balance = current_balance + total_wrongly_deducted
        print(f"\nTotal wrongly deducted: ${total_wrongly_deducted:.4f}")
        print(f"Corrected balance: ${corrected_balance:.4f}")

        # Apply correction
        conn.execute(
            "INSERT OR REPLACE INTO agent_state (key, value) VALUES (?, ?)",
            ("balance", str(round(corrected_balance, 4)))
        )

        # Log the correction in balance_history
        from datetime import datetime
        conn.execute(
            "INSERT INTO balance_history (timestamp, balance, pnl, event, cycle) VALUES (?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), round(corrected_balance, 4),
             round(total_wrongly_deducted, 4),
             f"BALANCE_CORRECTION: restored ${total_wrongly_deducted:.2f} wrongly deducted margin", 0)
        )
        conn.commit()

        print(f"\n✅ Balance corrected: ${current_balance:.2f} → ${corrected_balance:.2f}")
        print("You can now restart the bot safely.")

if __name__ == "__main__":
    fix_balance()
