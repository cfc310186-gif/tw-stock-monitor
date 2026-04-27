"""Instrument type classification.

We deliberately avoid heuristics like "all-digit symbols are stocks" — TW
active ETFs, warrants, and ETN codes can be mostly numeric but still need
distinct routing, and overseas futures use letter-only tickers. The watchlist
config tells us the type explicitly, this module just defines the type
vocabulary and per-type metadata.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from enum import Enum


class InstrumentType(str, Enum):
    STOCK = "stock"                      # 上市櫃 + ETF + 主動式 ETF + 權證 (any TWSE/TPEx instrument)
    DOMESTIC_FUTURES = "domestic_futures"  # TAIFEX: TXF / MXF / EXF / FXF / TXO …
    OVERSEAS_FUTURES = "overseas_futures"  # CME / CBOT / Eurex / SGX … (broker stub)


# Trading-hour windows used by both the kbar filter and the scheduler.
# (start, end) inclusive in Asia/Taipei.
@dataclass(frozen=True)
class SessionWindow:
    start: time
    end: time

    def contains(self, t: time) -> bool:
        if self.start <= self.end:
            return self.start <= t <= self.end
        # crosses midnight (e.g. futures night session)
        return t >= self.start or t <= self.end


# ---------------------------------------------------------------------------
# Per-type session profiles
# ---------------------------------------------------------------------------
# Stock regular session (集合競價 09:00 / 13:25-13:30 excluded for safety).
STOCK_KBAR_WINDOW = SessionWindow(time(9, 0), time(13, 30))
STOCK_POLL_WINDOW = SessionWindow(time(9, 1), time(13, 25))

# Domestic futures day session 08:45-13:45 + night 15:00-05:00 (next day).
DOMESTIC_FUTURES_DAY_KBAR = SessionWindow(time(8, 45), time(13, 45))
DOMESTIC_FUTURES_DAY_POLL = SessionWindow(time(8, 46), time(13, 44))
DOMESTIC_FUTURES_NIGHT_KBAR = SessionWindow(time(15, 0), time(5, 0))   # crosses midnight
DOMESTIC_FUTURES_NIGHT_POLL = SessionWindow(time(15, 1), time(4, 59))

# Overseas futures (CME Globex approximation) — Mon-Fri ~24h with a
# 05:00-06:00 Taipei maintenance break. Saturday closes at 05:00.
OVERSEAS_FUTURES_KBAR = SessionWindow(time(6, 0), time(5, 0))
OVERSEAS_FUTURES_POLL = SessionWindow(time(6, 1), time(4, 59))


def kbar_windows(t: InstrumentType) -> list[SessionWindow]:
    if t is InstrumentType.STOCK:
        return [STOCK_KBAR_WINDOW]
    if t is InstrumentType.DOMESTIC_FUTURES:
        return [DOMESTIC_FUTURES_DAY_KBAR, DOMESTIC_FUTURES_NIGHT_KBAR]
    if t is InstrumentType.OVERSEAS_FUTURES:
        return [OVERSEAS_FUTURES_KBAR]
    raise ValueError(f"Unknown instrument type: {t}")


def poll_windows(t: InstrumentType) -> list[SessionWindow]:
    if t is InstrumentType.STOCK:
        return [STOCK_POLL_WINDOW]
    if t is InstrumentType.DOMESTIC_FUTURES:
        return [DOMESTIC_FUTURES_DAY_POLL, DOMESTIC_FUTURES_NIGHT_POLL]
    if t is InstrumentType.OVERSEAS_FUTURES:
        return [OVERSEAS_FUTURES_POLL]
    raise ValueError(f"Unknown instrument type: {t}")
