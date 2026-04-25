from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Asia/Taipei")
_OPEN = time(9, 1)    # skip 09:00 集合競價
_CLOSE = time(13, 25)  # stop before 13:25–13:30 尾盤集合競價


def now_taipei() -> datetime:
    return datetime.now(tz=_TZ)


def is_trading_day(dt: datetime | None = None) -> bool:
    """Mon–Fri only (public holidays not handled — monitor will just run idle)."""
    return (dt or now_taipei()).weekday() < 5


def is_market_open(dt: datetime | None = None) -> bool:
    dt = dt or now_taipei()
    return is_trading_day(dt) and _OPEN <= dt.time() <= _CLOSE


def seconds_until_open(dt: datetime | None = None) -> float:
    """Seconds until next 09:01 on a trading day. Returns 0 if already open."""
    dt = dt or now_taipei()
    if is_market_open(dt):
        return 0.0
    next_open = dt.replace(hour=_OPEN.hour, minute=_OPEN.minute, second=0, microsecond=0)
    if dt.time() >= _CLOSE or not is_trading_day(dt):
        next_open += timedelta(days=1)
        while next_open.weekday() >= 5:
            next_open += timedelta(days=1)
    return max(0.0, (next_open - dt).total_seconds())


def seconds_until_close(dt: datetime | None = None) -> float:
    """Seconds remaining until 13:25. Returns 0 if already past close."""
    dt = dt or now_taipei()
    close_today = dt.replace(hour=_CLOSE.hour, minute=_CLOSE.minute, second=0, microsecond=0)
    return max(0.0, (close_today - dt).total_seconds())
