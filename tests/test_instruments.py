"""Tests for InstrumentType session-window helpers."""
from datetime import time

from monitor.instruments import (
    DOMESTIC_FUTURES_DAY_KBAR,
    DOMESTIC_FUTURES_NIGHT_KBAR,
    InstrumentType,
    SessionWindow,
    kbar_windows,
    poll_windows,
)


def test_session_window_same_day():
    w = SessionWindow(time(9, 0), time(13, 30))
    assert w.contains(time(9, 0)) is True
    assert w.contains(time(13, 30)) is True
    assert w.contains(time(14, 0)) is False
    assert w.contains(time(8, 59)) is False


def test_session_window_crosses_midnight():
    """Domestic futures night session 15:00 → 05:00 next day."""
    w = SessionWindow(time(15, 0), time(5, 0))
    assert w.contains(time(15, 0)) is True
    assert w.contains(time(20, 0)) is True
    assert w.contains(time(2, 0)) is True
    assert w.contains(time(5, 0)) is True
    assert w.contains(time(6, 0)) is False
    assert w.contains(time(14, 0)) is False


def test_kbar_windows_per_type():
    assert len(kbar_windows(InstrumentType.STOCK)) == 1
    assert len(kbar_windows(InstrumentType.DOMESTIC_FUTURES)) == 2
    assert len(kbar_windows(InstrumentType.OVERSEAS_FUTURES)) == 1


def test_domestic_futures_has_day_and_night_session():
    windows = kbar_windows(InstrumentType.DOMESTIC_FUTURES)
    assert DOMESTIC_FUTURES_DAY_KBAR in windows
    assert DOMESTIC_FUTURES_NIGHT_KBAR in windows


def test_poll_windows_match_kbar_windows_count():
    """Poll window count should match kbar window count per type."""
    for t in InstrumentType:
        assert len(poll_windows(t)) == len(kbar_windows(t))
