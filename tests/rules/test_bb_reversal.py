"""Unit tests for BbReversalRule.

Strategy: build synthetic bars so we can fully control whether each of the
five conditions (outside-prev / colour-flip / inside-cur / engulf-prev /
volume-surge) is met or not. Default fixture is a deep-bullish-engulfing
case at the lower band with elevated volume, so all gates pass.
"""
import pandas as pd
import pytest

from monitor.rules.bb_reversal import BbReversalRule


def _make_bars(
    n_base: int = 22,
    base_price: float = 100.0,
    prev_open: float = 100.0,
    prev_close: float = 86.0,    # below lower BB; deep enough that engulf-back is feasible
    cur_open: float = 85.0,
    cur_close: float = 101.0,    # green K, back inside BB AND > prev_open (engulf)
    base_volume: int = 1000,
    prev_volume: int = 1500,
    cur_volume: int = 3000,      # ratio ≈ 3000/1075 ≈ 2.79× → clears 1.5× gate
) -> pd.DataFrame:
    """Build a DataFrame with n_base stable bars then a prev and cur bar."""
    rows = [
        {"open": base_price, "high": base_price + 0.5, "low": base_price - 0.5,
         "close": base_price, "volume": base_volume}
        for _ in range(n_base)
    ]

    rows.append({"open": prev_open,
                 "high": max(prev_open, prev_close) + 0.2,
                 "low": min(prev_open, prev_close) - 0.2,
                 "close": prev_close, "volume": prev_volume})
    rows.append({"open": cur_open,
                 "high": max(cur_open, cur_close) + 0.2,
                 "low": min(cur_open, cur_close) - 0.2,
                 "close": cur_close, "volume": cur_volume})

    idx = pd.date_range(
        "2024-01-02 09:01", periods=len(rows), freq="1min", tz="Asia/Taipei", name="ts"
    )
    return pd.DataFrame(rows, index=idx)


_RULE = BbReversalRule(name="bb_reversal_5m", timeframe="5m", side="lower",
                       period=20, stddev=2.0)


def test_triggers_on_valid_lower_reversal():
    df = _make_bars()
    sig = _RULE.evaluate("2330", df)
    assert sig is not None
    assert sig.symbol == "2330"
    assert sig.rule_name == "bb_reversal_5m"
    assert "下軌外" in sig.message
    assert "紅K" in sig.message
    assert "吞噬" in sig.message


def test_no_trigger_insufficient_bars():
    df = _make_bars(n_base=15)  # 15 base + 2 = 17 < period(20) + 2
    assert _RULE.evaluate("2330", df) is None


def test_no_trigger_prev_inside_bb():
    df = _make_bars(prev_open=100.0, prev_close=99.9, cur_open=99.5, cur_close=100.2)
    assert _RULE.evaluate("2330", df) is None


def test_no_trigger_same_colour():
    df = _make_bars(
        prev_open=100.0, prev_close=86.0,  # red (close<open)
        cur_open=92.0, cur_close=89.0,     # also red
    )
    assert _RULE.evaluate("2330", df) is None


def test_no_trigger_cur_still_outside_bb():
    df = _make_bars(
        prev_open=100.0, prev_close=86.0,
        cur_open=85.0, cur_close=87.0,     # green but still below BB lower
    )
    assert _RULE.evaluate("2330", df) is None


def test_no_trigger_when_no_engulf():
    """Reversal not decisive: cur close lifts but doesn't pass prev open."""
    df = _make_bars(
        prev_open=100.0, prev_close=86.0,
        cur_open=85.0, cur_close=96.0,     # green, inside BB, but 96 < prev_open (100)
    )
    assert _RULE.evaluate("2330", df) is None


def test_no_trigger_when_volume_low():
    """All price conditions met, but cur volume not elevated → suppressed."""
    df = _make_bars(cur_volume=1000)       # ratio ≈ 1000/1025 < 1.5×
    assert _RULE.evaluate("2330", df) is None


def test_volume_threshold_configurable():
    rule = BbReversalRule(name="x", timeframe="5m", side="lower",
                          period=20, stddev=2.0, min_volume_ratio=5.0)
    df = _make_bars()                      # default vol ratio ≈ 2.8× < 5×
    assert rule.evaluate("2330", df) is None


def test_upper_side_triggers():
    rule_upper = BbReversalRule(
        name="bb_reversal_upper_5m", timeframe="5m", side="upper",
        period=20, stddev=2.0,
    )
    # prev: green K well above upper BB
    # cur: red K back inside, close < prev_open (engulf upper)
    df = _make_bars(
        prev_open=100.0, prev_close=115.0,  # green, above upper BB
        cur_open=116.0, cur_close=99.0,     # red, back inside, 99 < 100 (engulf)
    )
    sig = rule_upper.evaluate("2330", df)
    assert sig is not None
    assert "上軌外" in sig.message
    assert "黑K" in sig.message


def test_signal_fields():
    df = _make_bars()
    sig = _RULE.evaluate("2330", df)
    assert sig is not None
    assert {"close", "prev_open", "bb_upper", "bb_lower",
            "volume", "vol_ratio"}.issubset(sig.details)
    assert sig.details["prev_open"] == pytest.approx(100.0)
    assert sig.details["vol_ratio"] >= 1.5


def test_from_config():
    cfg = {"name": "bb_reversal_5m", "timeframe": "5m", "side": "lower",
           "period": 20, "stddev": 2.0, "cooldown_minutes": 30,
           "min_volume_ratio": 2.0}
    rule = BbReversalRule.from_config(cfg)
    assert rule.name == "bb_reversal_5m"
    assert rule.cooldown_minutes == 30
    assert rule._min_volume_ratio == 2.0


def test_from_config_uses_default_volume_ratio():
    cfg = {"name": "bb_reversal_5m", "timeframe": "5m", "side": "lower",
           "period": 20, "stddev": 2.0}
    rule = BbReversalRule.from_config(cfg)
    assert rule._min_volume_ratio == 1.5
