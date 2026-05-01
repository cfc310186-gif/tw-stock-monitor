from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from loguru import logger

from monitor.rules.base import Signal

_DDL = """
CREATE TABLE IF NOT EXISTS signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT    NOT NULL,
    rule_name       TEXT    NOT NULL,
    timeframe       TEXT    NOT NULL,
    bar_close_time  TEXT    NOT NULL,
    triggered_at    TEXT    NOT NULL,
    message         TEXT    NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dedup
    ON signals (symbol, rule_name, timeframe, bar_close_time);
"""


class SignalStore:
    """Persists triggered signals to SQLite for dedup across restarts."""

    def __init__(self, db_path: str | Path = "signals.db") -> None:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_DDL)
        self._conn.commit()
        logger.info("SignalStore opened: {}", db_path)

    def save(self, sig: Signal, triggered_at: datetime | None = None) -> bool:
        """Insert signal. Returns True if new, False if duplicate (already sent)."""
        triggered_at = triggered_at or datetime.now()
        try:
            self._conn.execute(
                "INSERT INTO signals "
                "(symbol, rule_name, timeframe, bar_close_time, triggered_at, message) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    sig.symbol,
                    sig.rule_name,
                    sig.timeframe,
                    _iso(sig.bar_close_time),
                    _iso(triggered_at),
                    sig.message,
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def recent_dedup_keys(self, since: datetime) -> set[tuple]:
        """Return dedup keys for signals triggered since `since`.

        Used at startup to restore RuleEngine._seen from DB so signals
        are not re-sent after a restart within the same trading session.
        """
        rows = self._conn.execute(
            "SELECT symbol, rule_name, timeframe, bar_close_time "
            "FROM signals WHERE triggered_at >= ?",
            (_iso(since),),
        ).fetchall()

        keys: set[tuple] = set()
        for sym, rule, tf, bar_ts_str in rows:
            try:
                bar_ts = datetime.fromisoformat(bar_ts_str)
            except ValueError:
                continue
            keys.add((sym, rule, tf, bar_ts))
        return keys

    def close(self) -> None:
        self._conn.close()


def _iso(dt: datetime) -> str:
    return dt.isoformat()
