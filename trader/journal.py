"""Trade journal: every decision, order, fill and rejection, with AUD values for tax.

Stored in SQLite so it's one file, easy to back up, and readable by a spreadsheet via
`python -m trader.runner --export-trades trades.csv`.
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY,
    ts_utc TEXT NOT NULL,
    mode TEXT NOT NULL,
    strategy TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price_usd REAL NOT NULL,
    fee_usd REAL NOT NULL,
    usd_per_aud REAL NOT NULL,
    value_aud REAL NOT NULL,
    fee_aud REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    ts_utc TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS equity (
    day TEXT PRIMARY KEY,
    equity_usd REAL NOT NULL,
    start_of_day_usd REAL NOT NULL,
    peak_usd REAL NOT NULL,
    orders INTEGER NOT NULL DEFAULT 0
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Journal:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.executescript(SCHEMA)

    def trade(self, mode, strategy, symbol, side, quantity, price_usd, fee_usd, usd_per_aud):
        value_aud = quantity * price_usd / usd_per_aud
        self.db.execute(
            "INSERT INTO trades (ts_utc, mode, strategy, symbol, side, quantity, price_usd,"
            " fee_usd, usd_per_aud, value_aud, fee_aud) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (_now(), mode, strategy, symbol, side, quantity, price_usd, fee_usd, usd_per_aud,
             value_aud, fee_usd / usd_per_aud))
        self.db.commit()

    def event(self, level: str, message: str):
        self.db.execute("INSERT INTO events (ts_utc, level, message) VALUES (?,?,?)",
                        (_now(), level, message))
        self.db.commit()

    def day_state(self, day: str, equity: float) -> tuple[float, float, int]:
        """Returns (start_of_day_equity, peak_equity, orders_today), creating today's row."""
        row = self.db.execute("SELECT start_of_day_usd, peak_usd, orders FROM equity WHERE day=?",
                              (day,)).fetchone()
        if row:
            return row
        prev_peak = self.db.execute("SELECT MAX(peak_usd) FROM equity").fetchone()[0] or equity
        peak = max(prev_peak, equity)
        self.db.execute("INSERT INTO equity VALUES (?,?,?,?,0)", (day, equity, equity, peak))
        self.db.commit()
        return equity, peak, 0

    def update_day(self, day: str, equity: float, orders_added: int = 0):
        self.db.execute(
            "UPDATE equity SET equity_usd=?, peak_usd=MAX(peak_usd, ?), orders=orders+? WHERE day=?",
            (equity, equity, orders_added, day))
        self.db.commit()

    def export_trades(self, out: Path):
        cur = self.db.execute("SELECT * FROM trades ORDER BY id")
        with open(out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([d[0] for d in cur.description])
            w.writerows(cur)
