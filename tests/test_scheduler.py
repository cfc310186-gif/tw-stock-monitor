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


# ---------------------------------------------------------------------------
# Per-instrument-type session checks
# ---------------------------------------------------------------------------

from monitor.instruments import InstrumentType


def test_stock_in_session_only_during_stock_hours():
    assert scheduler.is_in_session(InstrumentType.STOCK, _dt(0, 10, 0)) is True
    assert scheduler.is_in_session(InstrumentType.STOCK, _dt(0, 8, 50)) is False
    assert scheduler.is_in_session(InstrumentType.STOCK, _dt(0, 14, 0)) is False
    assert scheduler.is_in_session(InstrumentType.STOCK, _dt(5, 10, 0)) is False


def test_domestic_futures_day_session():
    # Mon 09:00 — both stocks AND futures are open
    assert scheduler.is_in_session(InstrumentType.DOMESTIC_FUTURES, _dt(0, 9, 0)) is True
    # Mon 08:50 — stock closed, futures day session open
    assert scheduler.is_in_session(InstrumentType.DOMESTIC_FUTURES, _dt(0, 8, 50)) is True
    # Mon 13:40 — stock closed, futures still open until 13:44
    assert scheduler.is_in_session(InstrumentType.DOMESTIC_FUTURES, _dt(0, 13, 40)) is True


def test_domestic_futures_night_session():
    # Mon 20:00 — night session active
    assert scheduler.is_in_session(InstrumentType.DOMESTIC_FUTURES, _dt(0, 20, 0)) is True
    # Tue 03:00 — still in Monday's night session (crosses midnight)
    assert scheduler.is_in_session(InstrumentType.DOMESTIC_FUTURES, _dt(1, 3, 0)) is True
    # Tue 06:00 — night session ended at 05:00, day session starts at 08:46
    assert scheduler.is_in_session(InstrumentType.DOMESTIC_FUTURES, _dt(1, 6, 0)) is False


def test_overseas_futures_continuous_weekday():
    # Mon 12:00 — open
    assert scheduler.is_in_session(InstrumentType.OVERSEAS_FUTURES, _dt(0, 12, 0)) is True
    # Mon 22:00 — open
    assert scheduler.is_in_session(InstrumentType.OVERSEAS_FUTURES, _dt(0, 22, 0)) is True
    # Tue 03:00 — open
    assert scheduler.is_in_session(InstrumentType.OVERSEAS_FUTURES, _dt(1, 3, 0)) is True
    # Daily 05:00-06:00 maintenance break
    assert scheduler.is_in_session(InstrumentType.OVERSEAS_FUTURES, _dt(1, 5, 30)) is False


def test_overseas_futures_weekend_closure():
    # Sat 04:00 — still in Friday's roll, OK
    assert scheduler.is_in_session(InstrumentType.OVERSEAS_FUTURES, _dt(5, 4, 0)) is True
    # Sat 12:00 — closed for the weekend
    assert scheduler.is_in_session(InstrumentType.OVERSEAS_FUTURES, _dt(5, 12, 0)) is False
    # Sun 22:00 — still closed (CME-Globex like markets reopen Mon ~06:00 Taipei)
    assert scheduler.is_in_session(InstrumentType.OVERSEAS_FUTURES, _dt(6, 22, 0)) is False


def test_any_in_session_unions_types():
    types = [InstrumentType.STOCK, InstrumentType.DOMESTIC_FUTURES]
    # Mon 08:50 — stock closed, dfut open → union = open
    assert scheduler.any_in_session(types, _dt(0, 8, 50)) is True
    # Mon 14:00 — both closed
    assert scheduler.any_in_session(types, _dt(0, 14, 0)) is False


def test_seconds_until_next_open_returns_zero_when_active():
    types = [InstrumentType.STOCK]
    assert scheduler.seconds_until_next_open(types, _dt(0, 10, 0)) == 0.0


def test_seconds_until_next_open_finds_next_window():
    types = [InstrumentType.STOCK]
    # Mon 08:00 → 61 min until stock 09:01
    secs = scheduler.seconds_until_next_open(types, _dt(0, 8, 0))
    assert 60 * 60 <= secs <= 62 * 60
