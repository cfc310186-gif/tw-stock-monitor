"""Unit tests for BbReversalRule.

Strategy: build synthetic bars so we can fully control whether each of the
three conditions (outside-prev / colour-flip / inside-cur) is met or not.
We use 20 constant bars to establish a tight BB, then craft prev & cur bars.
"""
import pandas as pd
import pytest

from monitor.rules.bb_reversal import BbReversalRule


def _make_bars(
    n_base: int = 22,
    base_price: float = 100.0,
    prev_open: float = 100.0,
    prev_close: float = 90.0,   # default: below lower BB (red K going down)
    cur_open: float = 88.0,
    cur_close: float = 96.0,    # default: green K, inside BB
) -> pd.DataFrame:
    """Build a DataFrame with n_base stable bars then a prev and cur bar."""
    prices = [base_price] * n_base
    idx = pd.date_range("2024-01-02 09:01", periods=n_base, freq="1min", tz="Asia/Taipei")

    rows = [
        {"open": p, "high": p + 0.5, "low": p - 0.5, "close": p, "volume": 1000}
        for p in prices
    ]

    # prev bar (index n_base)
    rows.append({"open": prev_open, "high": max(prev_open, prev_close) + 0.2,
                 "low": min(prev_open, prev_close) - 0.2, "close": prev_close, "volume": 2000})
    # cur bar (index n_base + 1)
    rows.append({"open": cur_open, "high": max(cur_open, cur_close) + 0.2,
                 "low": min(cur_open, cur_close) - 0.2, "close": cur_close, "volume": 3000})

    idx = pd.date_range(
        "2024-01-02 09:01", periods=len(rows), freq="1min", tz="Asia/Taipei", name="ts"
    )
    return pd.DataFrame(rows, index=idx)


_RULE = BbReversalRule(name="bb_reversal_5m", timeframe="5m", side="lower", period=20, stddev=2.0)


def test_triggers_on_valid_lower_reversal():
    df = _make_bars()
    # prev: red K (close=90 < open=100), outside lower BB (base=100, std≈0 → lower≈100)
    # cur: green K (close=96 > open=88), inside BB
    sig = _RULE.evaluate("2330", df)
    assert sig is not None
    assert sig.symbol == "2330"
    assert sig.rule_name == "bb_reversal_5m"
    assert "下軌外" in sig.message
    assert "紅K" in sig.message


def test_no_trigger_insufficient_bars():
    df = _make_bars(n_base=15)  # 15 base + 2 = 17 < period(20) + 2
    sig = _RULE.evaluate("2330", df)
    assert sig is None


def test_no_trigger_prev_inside_bb():
    # prev close=99.9, still inside BB → condition 1 fails
    df = _make_bars(prev_open=100.0, prev_close=99.9, cur_open=99.5, cur_close=100.2)
    sig = _RULE.evaluate("2330", df)
    assert sig is None


def test_no_trigger_same_colour():
    # prev red, cur also red → colour flip condition fails
    df = _make_bars(
        prev_open=100.0, prev_close=90.0,   # red
        cur_open=92.0, cur_close=89.0,      # also red (close < open)
    )
    sig = _RULE.evaluate("2330", df)
    assert sig is None


def test_no_trigger_cur_still_outside_bb():
    # cur bar still below lower BB → condition 3 fails
    df = _make_bars(
        prev_open=100.0, prev_close=88.0,   # red, below BB
        cur_open=85.0, cur_close=87.0,      # green but still below BB
    )
    sig = _RULE.evaluate("2330", df)
    assert sig is None


def test_upper_side_triggers():
    rule_upper = BbReversalRule(
        name="bb_reversal_upper_5m", timeframe="5m", side="upper", period=20, stddev=2.0
    )
    # prev: green K well above upper BB; cur: red K back inside
    df = _make_bars(
        prev_open=100.0, prev_close=115.0,   # green, well above upper BB
        cur_open=116.0, cur_close=101.0,     # red, back inside
    )
    sig = rule_upper.evaluate("2330", df)
    assert sig is not None
    assert "上軌外" in sig.message
    assert "黑K" in sig.message


def test_signal_fields():
    df = _make_bars()
    sig = _RULE.evaluate("2330", df)
    assert sig is not None
    assert {"close", "bb_upper", "bb_lower", "volume", "vol_ratio"}.issubset(sig.details)


def test_from_config():
    cfg = {"name": "bb_reversal_5m", "timeframe": "5m", "side": "lower",
           "period": 20, "stddev": 2.0, "cooldown_minutes": 30}
    rule = BbReversalRule.from_config(cfg)
    assert rule.name == "bb_reversal_5m"
    assert rule.cooldown_minutes == 30
