"""Unit tests for RangeBreakoutRule."""
from __future__ import annotations

import pandas as pd
import pytest

from monitor.rules.range_breakout import RangeBreakoutRule


def _bars(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[int] | None = None,
) -> pd.DataFrame:
    n = len(closes)
    assert len(highs) == n and len(lows) == n
    if volumes is None:
        # Default: flat baseline + 3× cur bar so the volume gate passes.
        volumes = [1000] * (n - 1) + [3000]
    assert len(volumes) == n
    idx = pd.date_range(
        "2024-01-02 09:01", periods=n, freq="1min", tz="Asia/Taipei", name="ts"
    )
    return pd.DataFrame(
        {"open": closes, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )


def test_upside_breakout_triggers():
    highs = [100.0] * 21 + [99.5, 102.5]
    lows = [98.0] * 23
    closes = [99.5] * 21 + [99.0, 102.0]
    df = _bars(highs, lows, closes)

    rule = RangeBreakoutRule(name="range_breakout_up_15m", timeframe="15m",
                             period=20, direction="up")
    sig = rule.evaluate("2330", df)
    assert sig is not None
    assert "突破" in sig.message
    assert "量增確認" in sig.message
    assert sig.details["close"] == pytest.approx(102.0)
    assert sig.details["level"] == pytest.approx(100.0)


def test_no_trigger_when_already_above():
    highs = [100.0] * 21 + [102.0, 103.0]
    lows = [98.0] * 23
    closes = [99.5] * 21 + [102.0, 103.0]
    df = _bars(highs, lows, closes)

    rule = RangeBreakoutRule(name="x", timeframe="15m", period=20, direction="up")
    assert rule.evaluate("2330", df) is None


def test_no_trigger_when_close_within_range():
    highs = [100.0] * 23
    lows = [98.0] * 23
    closes = [99.0] * 23
    df = _bars(highs, lows, closes)
    rule = RangeBreakoutRule(name="x", timeframe="15m", period=20, direction="up")
    assert rule.evaluate("2330", df) is None


def test_no_trigger_when_volume_low():
    """Price-only breakout with no volume surge → suppressed (fake breakout)."""
    highs = [100.0] * 21 + [99.5, 102.5]
    lows = [98.0] * 23
    closes = [99.5] * 21 + [99.0, 102.0]
    volumes = [1000] * 23  # cur volume == baseline
    df = _bars(highs, lows, closes, volumes=volumes)
    rule = RangeBreakoutRule(name="x", timeframe="15m", period=20, direction="up")
    assert rule.evaluate("2330", df) is None


def test_volume_threshold_configurable():
    highs = [100.0] * 21 + [99.5, 102.5]
    lows = [98.0] * 23
    closes = [99.5] * 21 + [99.0, 102.0]
    df = _bars(highs, lows, closes)  # default cur vol = 3× baseline

    strict = RangeBreakoutRule(name="x", timeframe="15m", period=20,
                               direction="up", min_volume_ratio=5.0)
    assert strict.evaluate("2330", df) is None  # 3× < 5×

    lax = RangeBreakoutRule(name="x", timeframe="15m", period=20,
                            direction="up", min_volume_ratio=1.0)
    assert lax.evaluate("2330", df) is not None


def test_downside_breakout_triggers():
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
    assert sig.details["vol_ratio"] >= 1.5


def test_from_config():
    cfg = {"name": "range_breakout_up_15m", "timeframe": "15m",
           "period": 30, "direction": "up", "cooldown_minutes": 60,
           "min_volume_ratio": 2.0}
    rule = RangeBreakoutRule.from_config(cfg)
    assert rule.name == "range_breakout_up_15m"
    assert rule.cooldown_minutes == 60
    assert rule._period == 30
    assert rule._min_volume_ratio == 2.0


def test_from_config_uses_default_volume_ratio():
    cfg = {"name": "rb", "timeframe": "15m", "period": 20, "direction": "up"}
    rule = RangeBreakoutRule.from_config(cfg)
    assert rule._min_volume_ratio == 1.5


def test_invalid_direction():
    with pytest.raises(ValueError):
        RangeBreakoutRule(name="x", timeframe="15m", period=20, direction="sideways")


def test_invalid_period():
    with pytest.raises(ValueError):
        RangeBreakoutRule(name="x", timeframe="15m", period=1, direction="up")
