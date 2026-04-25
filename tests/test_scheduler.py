from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from monitor import scheduler

_TZ = ZoneInfo("Asia/Taipei")


def _dt(weekday: int, hour: int, minute: int) -> datetime:
    """Build a tz-aware datetime. weekday: 0=Mon … 6=Sun."""
    # 2024-01-01 is a Monday (weekday=0)
    base = datetime(2024, 1, 1, tzinfo=_TZ)
    from datetime import timedelta
    return base + timedelta(days=weekday, hours=hour, minutes=minute)


def test_trading_day_weekdays():
    for wd in range(5):  # Mon–Fri
        assert scheduler.is_trading_day(_dt(wd, 10, 0))


def test_not_trading_day_weekend():
    assert not scheduler.is_trading_day(_dt(5, 10, 0))   # Saturday
    assert not scheduler.is_trading_day(_dt(6, 10, 0))   # Sunday


def test_market_open_during_session():
    assert scheduler.is_market_open(_dt(0, 10, 0))   # Mon 10:00


def test_market_open_at_boundary():
    assert scheduler.is_market_open(_dt(0, 9, 1))    # exactly at open
    assert scheduler.is_market_open(_dt(0, 13, 25))  # exactly at close


def test_market_closed_before_open():
    assert not scheduler.is_market_open(_dt(0, 8, 59))


def test_market_closed_after_close():
    assert not scheduler.is_market_open(_dt(0, 13, 26))


def test_market_closed_on_weekend():
    assert not scheduler.is_market_open(_dt(5, 10, 0))


def test_seconds_until_open_returns_zero_when_open():
    dt = _dt(0, 10, 0)
    assert scheduler.seconds_until_open(dt) == 0.0


def test_seconds_until_open_positive_before_open():
    dt = _dt(0, 8, 0)   # Mon 08:00 → 61 minutes until 09:01
    secs = scheduler.seconds_until_open(dt)
    assert 60 * 60 < secs <= 62 * 60


def test_seconds_until_close_positive():
    dt = _dt(0, 10, 0)   # 3h25min until 13:25
    secs = scheduler.seconds_until_close(dt)
    assert secs == pytest.approx(3 * 3600 + 25 * 60, abs=5)


def test_seconds_until_close_zero_after_close():
    dt = _dt(0, 14, 0)
    assert scheduler.seconds_until_close(dt) == 0.0
