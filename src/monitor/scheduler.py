"""Trading session helpers — type-aware.

Each instrument type has its own polling-window definition (see
monitor.instruments). The legacy stock-only helpers (`is_market_open`,
`seconds_until_open`, …) are kept as thin wrappers that target the stock
session, so existing tests and Plan-era code keep working. The new helpers
take an InstrumentType (or set of types) so the app loop can be type-aware.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from monitor.instruments import (
    InstrumentType,
    SessionWindow,
    poll_windows,
)

_TZ = ZoneInfo("Asia/Taipei")
_DAY = timedelta(days=1)


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def now_taipei() -> datetime:
    return datetime.now(tz=_TZ)


def is_trading_day(dt: datetime | None = None) -> bool:
    """Mon-Fri only. Public holidays not handled — monitor will idle."""
    return (dt or now_taipei()).weekday() < 5


def _normalise(dt: datetime | None) -> datetime:
    return dt or now_taipei()


# ---------------------------------------------------------------------------
# Per-type session checks
# ---------------------------------------------------------------------------

def is_in_session(itype: InstrumentType, dt: datetime | None = None) -> bool:
    """True if `dt` falls inside any polling window for this instrument type.

    Overseas futures session is approximated as Mon-Fri all-day with a
    daily 05:00-06:00 Taipei maintenance break, plus the broader weekend
    closure. Domestic-futures night session (15:00-05:00) crosses midnight,
    handled via SessionWindow.contains.
    """
    dt = _normalise(dt)
    if not _is_open_day(itype, dt):
        return False
    return any(w.contains(dt.time()) for w in poll_windows(itype))


def _is_open_day(itype: InstrumentType, dt: datetime) -> bool:
    """Filter weekends per instrument type.

    - Stocks / domestic futures: Mon-Fri only.
    - Overseas futures: closes Sat 05:00 Taipei, reopens Mon 06:00.
      Saturday before 05:00 still counts (rolling Friday session).
    """
    wd = dt.weekday()  # Mon=0 … Sun=6
    if itype in (InstrumentType.STOCK, InstrumentType.DOMESTIC_FUTURES):
        return wd < 5
    if itype is InstrumentType.OVERSEAS_FUTURES:
        if wd == 5:                          # Sat
            return dt.time() < time(5, 0)
        if wd == 6:                          # Sun
            return False
        return True
    return False


def any_in_session(types: Iterable[InstrumentType],
                   dt: datetime | None = None) -> bool:
    return any(is_in_session(t, dt) for t in types)


def seconds_until_next_open(types: Iterable[InstrumentType],
                            dt: datetime | None = None) -> float:
    """Seconds until ANY of the supplied types is next in session.

    Returns 0 if at least one type is already in session. Caps the search
    at 8 days to handle weekends + holidays defensively.
    """
    dt = _normalise(dt)
    types = list(types)
    if any_in_session(types, dt):
        return 0.0

    # Walk forward minute-by-minute up to 8 days. Coarse but simple and
    # correct given the few session windows we model.
    horizon = dt + 8 * _DAY
    cursor = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
    while cursor <= horizon:
        if any_in_session(types, cursor):
            return max(0.0, (cursor - dt).total_seconds())
        cursor += timedelta(minutes=1)
    return float("inf")


# ---------------------------------------------------------------------------
# Legacy stock-only helpers (kept for backwards compatibility)
# ---------------------------------------------------------------------------

# Stock poll window from instruments.STOCK_POLL_WINDOW.
_STOCK = poll_windows(InstrumentType.STOCK)[0]


def is_market_open(dt: datetime | None = None) -> bool:
    return is_in_session(InstrumentType.STOCK, dt)


def seconds_until_open(dt: datetime | None = None) -> float:
    """Seconds until next 09:01 on a trading day (stock session)."""
    dt = _normalise(dt)
    if is_market_open(dt):
        return 0.0
    next_open = dt.replace(hour=_STOCK.start.hour,
                           minute=_STOCK.start.minute,
                           second=0, microsecond=0)
    if dt.time() >= _STOCK.end or not is_trading_day(dt):
        next_open += _DAY
        while next_open.weekday() >= 5:
            next_open += _DAY
    return max(0.0, (next_open - dt).total_seconds())


def seconds_until_close(dt: datetime | None = None) -> float:
    """Seconds remaining until 13:25 (stock close)."""
    dt = _normalise(dt)
    close_today = dt.replace(hour=_STOCK.end.hour,
                             minute=_STOCK.end.minute,
                             second=0, microsecond=0)
    return max(0.0, (close_today - dt).total_seconds())
