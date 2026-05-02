"""Tests for the 1d (daily) timeframe — both the historical resample
and BarBuilder's intraday-evolving daily bar."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from monitor.data.bar_builder import BarBuilder
from monitor.data.historical import TIMEFRAMES, resample_bars

_TZ = ZoneInfo("Asia/Taipei")


# ---------------------------------------------------------------------------
# resample_bars(rule="1D")
# ---------------------------------------------------------------------------

def _two_day_1m() -> pd.DataFrame:
    """30 1-min bars across two trading days."""
    day1 = pd.date_range("2024-01-02 09:01", periods=15, freq="1min", tz=_TZ)
    day2 = pd.date_range("2024-01-03 09:01", periods=15, freq="1min", tz=_TZ)
    idx = pd.DatetimeIndex(list(day1) + list(day2), name="ts")
    closes = list(range(100, 115)) + list(range(110, 95, -1))
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 0.5 for c in closes],
            "low": [c - 0.5 for c in closes],
            "close": closes,
            "volume": [1000] * 30,
        },
        index=idx,
    )


def test_timeframes_includes_daily():
    assert "1d" in TIMEFRAMES
    assert TIMEFRAMES["1d"] == "1D"


def test_resample_daily_collapses_each_day():
    df_1m = _two_day_1m()
    daily = resample_bars(df_1m, "1D")
    assert len(daily) == 2
    # Day 1: closes 100..114 → open=100, close=114, high≈114.5
    assert daily.iloc[0]["open"] == pytest.approx(100.0)
    assert daily.iloc[0]["close"] == pytest.approx(114.0)
    assert daily.iloc[0]["volume"] == 15 * 1000
    # Day 2: closes 110..96 → open=110, close=96
    assert daily.iloc[1]["open"] == pytest.approx(110.0)
    assert daily.iloc[1]["close"] == pytest.approx(96.0)


def test_resample_daily_label_is_left():
    """Daily bar at 2024-01-02 should be labelled with 2024-01-02 (the
    trading day), not 2024-01-03 (next-day boundary)."""
    df_1m = _two_day_1m()
    daily = resample_bars(df_1m, "1D")
    assert daily.index[0].date().isoformat() == "2024-01-02"
    assert daily.index[1].date().isoformat() == "2024-01-03"


# ---------------------------------------------------------------------------
# BarBuilder daily bar maintenance
# ---------------------------------------------------------------------------

def _hist_with_daily(n_minutes: int = 30) -> dict[str, dict[str, pd.DataFrame]]:
    """Two-day 1m history + all timeframes resampled (incl. 1d)."""
    day1 = pd.date_range("2024-01-02 09:01", periods=n_minutes // 2,
                          freq="1min", tz=_TZ)
    day2 = pd.date_range("2024-01-03 09:01", periods=n_minutes // 2,
                          freq="1min", tz=_TZ)
    idx = pd.DatetimeIndex(list(day1) + list(day2), name="ts")
    closes = [100.0] * n_minutes
    df_1m = pd.DataFrame(
        {"open": closes, "high": [c + 0.5 for c in closes],
         "low": [c - 0.5 for c in closes], "close": closes,
         "volume": [1000] * n_minutes},
        index=idx,
    )
    frames: dict[str, pd.DataFrame] = {"1m": df_1m}
    for tf, rule in TIMEFRAMES.items():
        if rule is not None:
            frames[tf] = resample_bars(df_1m, rule)
    return {"2330": frames}


def test_bar_builder_loads_historical_daily():
    builder = BarBuilder(_hist_with_daily(n_minutes=30))
    daily = builder.get_bars("2330", "1d")
    assert len(daily) == 2  # two trading days


def test_daily_bar_extends_intraday():
    """Polling on a brand-new day should append a fresh today bar to the
    daily deque and update it on subsequent 1-min closes."""
    builder = BarBuilder(_hist_with_daily(n_minutes=30))
    base_len = len(builder.get_bars("2330", "1d"))

    # Simulate ticks crossing a 1-min boundary on 2024-01-04 (a new day).
    t1 = datetime(2024, 1, 4, 9, 30, 0, tzinfo=_TZ)
    t2 = datetime(2024, 1, 4, 9, 31, 0, tzinfo=_TZ)
    builder.on_snapshot("2330", 105.0, 1, t1)        # seeds pending bar
    closed = builder.on_snapshot("2330", 106.0, 100, t2)  # closes the 1-min

    assert "1m" in closed
    assert "1d" in closed
    daily = builder.get_bars("2330", "1d")
    assert len(daily) == base_len + 1
    last = daily.iloc[-1]
    assert last["close"] == pytest.approx(106.0)
    assert last["high"] >= 106.0


def test_daily_bar_replaces_tail_for_same_day():
    """Two minute closes on the same day update the SAME daily entry,
    not append two."""
    builder = BarBuilder(_hist_with_daily(n_minutes=30))
    base_len = len(builder.get_bars("2330", "1d"))

    t1 = datetime(2024, 1, 4, 9, 30, 0, tzinfo=_TZ)
    t2 = datetime(2024, 1, 4, 9, 31, 0, tzinfo=_TZ)
    t3 = datetime(2024, 1, 4, 9, 32, 0, tzinfo=_TZ)
    builder.on_snapshot("2330", 105.0, 1, t1)
    builder.on_snapshot("2330", 110.0, 100, t2)   # closes 1m: high=105
    builder.on_snapshot("2330", 95.0, 200, t3)    # closes 1m: low=95

    daily = builder.get_bars("2330", "1d")
    assert len(daily) == base_len + 1            # one new day, not two
    last = daily.iloc[-1]
    # high should reflect the highest among the closed 1-min bars seen so far
    assert last["high"] >= 105.0
    assert last["low"] <= 95.5    # a 1-min bar's low can be 95-0.5+epsilon
    assert last["close"] == pytest.approx(95.0)


def test_daily_bar_volume_aggregates():
    builder = BarBuilder(_hist_with_daily(n_minutes=30))
    t1 = datetime(2024, 1, 4, 9, 30, 0, tzinfo=_TZ)
    t2 = datetime(2024, 1, 4, 9, 31, 0, tzinfo=_TZ)
    t3 = datetime(2024, 1, 4, 9, 32, 0, tzinfo=_TZ)
    builder.on_snapshot("2330", 100.0, 1, t1)     # seed prev=1
    builder.on_snapshot("2330", 100.0, 201, t2)   # closes 1m vol=200
    builder.on_snapshot("2330", 100.0, 351, t3)   # closes 1m vol=150

    daily = builder.get_bars("2330", "1d")
    last = daily.iloc[-1]
    # Today's volume = sum of today's 1-min closed bars
    assert last["volume"] == 200 + 150
