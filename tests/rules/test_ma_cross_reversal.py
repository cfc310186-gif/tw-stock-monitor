"""Unit tests for MaCrossReversalRule.

Strategy: build synthetic close series where MA(short) crosses MA(long) at a
known position. SMA is easier to reason about than EMA, so most tests use
ma_type='sma' for clarity; one test confirms EMA works end-to-end.
"""
from __future__ import annotations

import pandas as pd
import pytest

from monitor.rules.ma_cross_reversal import MaCrossReversalRule


def _bars_from_closes(closes: list[float]) -> pd.DataFrame:
    n = len(closes)
    idx = pd.date_range(
        "2024-01-02 09:01", periods=n, freq="1min", tz="Asia/Taipei", name="ts"
    )
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 0.5 for c in closes],
            "low": [c - 0.5 for c in closes],
            "close": closes,
            "volume": [1000] * n,
        },
        index=idx,
    )


def test_golden_cross_triggers():
    # Pattern: 20 flat bars at 100 + a single 80 dip + 5 recovery bars at 100.
    # The dip pulls SMA5 below SMA20 immediately; once the 80 bar leaves the
    # 5-bar window (at idx 25) SMA5 jumps back to 100 and crosses SMA20 (~99).
    closes = [100.0] * 20 + [80.0, 100.0, 100.0, 100.0, 100.0, 100.0]
    df = _bars_from_closes(closes)
    rule = MaCrossReversalRule(
        name="ma_cross_reversal_up_5m", timeframe="5m",
        short=5, long=20, direction="up", ma_type="sma",
    )
    sig = rule.evaluate("2330", df)
    assert sig is not None
    assert "黃金交叉" in sig.message
    assert sig.details["close"] == pytest.approx(100.0)


def test_no_trigger_when_already_above():
    # SMA5 has been above SMA20 for many bars → no fresh cross on last bar
    closes = [100.0] * 20 + [105.0] * 10
    df = _bars_from_closes(closes)
    rule = MaCrossReversalRule(
        name="ma_cross_up", timeframe="5m",
        short=5, long=20, direction="up", ma_type="sma",
    )
    sig = rule.evaluate("2330", df)
    assert sig is None


def test_death_cross_triggers():
    # Mirror of the golden-cross pattern: 120 spike then recovery to 100.
    closes = [100.0] * 20 + [120.0, 100.0, 100.0, 100.0, 100.0, 100.0]
    df = _bars_from_closes(closes)
    rule = MaCrossReversalRule(
        name="ma_cross_reversal_down_5m", timeframe="5m",
        short=5, long=20, direction="down", ma_type="sma",
    )
    sig = rule.evaluate("2330", df)
    assert sig is not None
    assert "死亡交叉" in sig.message


def test_no_trigger_insufficient_bars():
    closes = [100.0] * 15  # < long(20) + 2
    df = _bars_from_closes(closes)
    rule = MaCrossReversalRule(name="x", timeframe="5m", short=5, long=20)
    assert rule.evaluate("2330", df) is None


def test_wrong_direction_no_trigger():
    # Golden-cross conditions but rule configured for direction='down'
    closes = [100.0] * 20 + [80.0, 100.0, 100.0, 100.0, 100.0, 100.0]
    df = _bars_from_closes(closes)
    rule = MaCrossReversalRule(
        name="x", timeframe="5m",
        short=5, long=20, direction="down", ma_type="sma",
    )
    assert rule.evaluate("2330", df) is None


def test_ema_cross_works():
    # Same dip-then-recovery pattern, but using EMA smoothing
    closes = [100.0] * 20 + [80.0, 100.0, 100.0, 100.0, 100.0, 100.0]
    df = _bars_from_closes(closes)
    rule = MaCrossReversalRule(
        name="x", timeframe="5m",
        short=5, long=20, direction="up", ma_type="ema",
    )
    sig = rule.evaluate("2330", df)
    assert sig is not None


def test_signal_fields():
    closes = [100.0] * 20 + [80.0, 100.0, 100.0, 100.0, 100.0, 100.0]
    df = _bars_from_closes(closes)
    rule = MaCrossReversalRule(
        name="ma_cross_reversal_up_5m", timeframe="5m",
        short=5, long=20, direction="up", ma_type="sma",
    )
    sig = rule.evaluate("2330", df)
    assert sig is not None
    assert {"close", "sma_5", "sma_20", "volume", "vol_ratio"}.issubset(sig.details)


def test_from_config():
    cfg = {
        "name": "ma_cross_reversal_up_5m", "timeframe": "5m",
        "short": 5, "long": 20, "direction": "up",
        "ma_type": "ema", "cooldown_minutes": 45,
    }
    rule = MaCrossReversalRule.from_config(cfg)
    assert rule.name == "ma_cross_reversal_up_5m"
    assert rule.cooldown_minutes == 45


def test_invalid_direction():
    with pytest.raises(ValueError):
        MaCrossReversalRule(name="x", timeframe="5m", direction="sideways")


def test_invalid_ma_type():
    with pytest.raises(ValueError):
        MaCrossReversalRule(name="x", timeframe="5m", ma_type="wma")


def test_short_must_be_less_than_long():
    with pytest.raises(ValueError):
        MaCrossReversalRule(name="x", timeframe="5m", short=20, long=20)
