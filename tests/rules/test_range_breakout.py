"""Unit tests for RangeBreakoutRule."""
from __future__ import annotations

import pandas as pd
import pytest

from monitor.rules.range_breakout import RangeBreakoutRule


def _bars(highs: list[float], lows: list[float], closes: list[float]) -> pd.DataFrame:
    n = len(closes)
    assert len(highs) == n and len(lows) == n
    idx = pd.date_range(
        "2024-01-02 09:01", periods=n, freq="1min", tz="Asia/Taipei", name="ts"
    )
    return pd.DataFrame(
        {
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1000] * n,
        },
        index=idx,
    )


def test_upside_breakout_triggers():
    # 22 prior bars with high ≤ 100, then current bar closes at 102 > 100.
    # prev bar (-2) close=99 < 100 (no prior breakout); cur close=102 > 100.
    highs = [100.0] * 21 + [99.5, 102.5]
    lows = [98.0] * 23
    closes = [99.5] * 21 + [99.0, 102.0]
    df = _bars(highs, lows, closes)

    rule = RangeBreakoutRule(name="range_breakout_up_15m", timeframe="15m",
                             period=20, direction="up")
    sig = rule.evaluate("2330", df)
    assert sig is not None
    assert "突破" in sig.message
    assert sig.details["close"] == pytest.approx(102.0)
    assert sig.details["level"] == pytest.approx(100.0)


def test_no_trigger_when_already_above():
    # Prev bar already broke above 100 → cur breakout suppressed
    highs = [100.0] * 21 + [102.0, 103.0]
    lows = [98.0] * 23
    closes = [99.5] * 21 + [102.0, 103.0]
    df = _bars(highs, lows, closes)

    rule = RangeBreakoutRule(name="x", timeframe="15m", period=20, direction="up")
    assert rule.evaluate("2330", df) is None


def test_no_trigger_when_close_within_range():
    # cur close = 99 (inside the 20-bar range)
    highs = [100.0] * 23
    lows = [98.0] * 23
    closes = [99.0] * 23
    df = _bars(highs, lows, closes)
    rule = RangeBreakoutRule(name="x", timeframe="15m", period=20, direction="up")
    assert rule.evaluate("2330", df) is None


def test_downside_breakout_triggers():
    # 22 prior bars low ≥ 95, then cur close=92 < 95
    highs = [100.0] * 23
    lows = [95.0] * 21 + [95.5, 92.0]
    closes = [97.0] * 21 + [96.0, 92.0]
    df = _bars(highs, lows, closes)

    rule = RangeBreakoutRule(name="range_breakout_down_15m", timeframe="15m",
                             period=20, direction="down")
    sig = rule.evaluate("2330", df)
    assert sig is not None
    assert "跌破" in sig.message
    assert sig.details["level"] == pytest.approx(95.0)


def test_no_trigger_insufficient_bars():
    closes = [100.0] * 10
    df = _bars([101.0] * 10, [99.0] * 10, closes)
    rule = RangeBreakoutRule(name="x", timeframe="15m", period=20, direction="up")
    assert rule.evaluate("2330", df) is None


def test_wrong_direction_no_trigger():
    highs = [100.0] * 21 + [99.5, 102.5]
    lows = [98.0] * 23
    closes = [99.5] * 21 + [99.0, 102.0]
    df = _bars(highs, lows, closes)
    rule = RangeBreakoutRule(name="x", timeframe="15m", period=20, direction="down")
    assert rule.evaluate("2330", df) is None


def test_signal_fields():
    highs = [100.0] * 21 + [99.5, 102.5]
    lows = [98.0] * 23
    closes = [99.5] * 21 + [99.0, 102.0]
    df = _bars(highs, lows, closes)
    rule = RangeBreakoutRule(name="rb_15m", timeframe="15m", period=20, direction="up")
    sig = rule.evaluate("2330", df)
    assert sig is not None
    assert {"close", "level", "volume", "vol_ratio"}.issubset(sig.details)


def test_from_config():
    cfg = {"name": "range_breakout_up_15m", "timeframe": "15m",
           "period": 30, "direction": "up", "cooldown_minutes": 60}
    rule = RangeBreakoutRule.from_config(cfg)
    assert rule.name == "range_breakout_up_15m"
    assert rule.cooldown_minutes == 60
    assert rule._period == 30


def test_invalid_direction():
    with pytest.raises(ValueError):
        RangeBreakoutRule(name="x", timeframe="15m", period=20, direction="sideways")


def test_invalid_period():
    with pytest.raises(ValueError):
        RangeBreakoutRule(name="x", timeframe="15m", period=1, direction="up")
