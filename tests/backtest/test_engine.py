"""Tests for the backtest engine."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from monitor.backtest.engine import (
    BacktestResult,
    TradeOutcome,
    _compute_outcome,
    _infer_direction,
    backtest_rule,
    backtest_yaml,
)
from monitor.rules.base import Rule, Signal
from monitor.rules.bb_reversal import BbReversalRule
from monitor.rules.ma_cross_reversal import MaCrossReversalRule
from monitor.rules.range_breakout import RangeBreakoutRule

_TZ = ZoneInfo("Asia/Taipei")


def _bars(closes: list[float], highs=None, lows=None) -> pd.DataFrame:
    n = len(closes)
    highs = highs if highs is not None else [c + 0.5 for c in closes]
    lows = lows if lows is not None else [c - 0.5 for c in closes]
    idx = pd.date_range(
        "2024-01-02 09:01", periods=n, freq="1min", tz="Asia/Taipei", name="ts"
    )
    return pd.DataFrame(
        {"open": closes, "high": highs, "low": lows,
         "close": closes, "volume": [1000] * n},
        index=idx,
    )


def _signal(ts) -> Signal:
    return Signal(
        symbol="2330", rule_name="r", timeframe="5m",
        bar_close_time=ts, message="x",
    )


# ---------------------------------------------------------------------------
# _compute_outcome
# ---------------------------------------------------------------------------

def test_long_outcome_hit():
    # Entry at 100, then climbs to 102 → +2% > 0.5% threshold → hit
    closes = [100.0, 101.0, 102.0, 102.0]
    df = _bars(closes)
    sig = _signal(df.index[0])
    out = _compute_outcome(sig, df, idx=0, direction="long",
                           horizon=3, threshold_pct=0.5)
    assert out is not None
    assert out.entry_price == pytest.approx(100.0)
    assert out.exit_price == pytest.approx(102.0)
    assert out.return_pct == pytest.approx(2.0)
    assert out.mfe_pct == pytest.approx(2.5)   # high reaches 102.5
    assert out.hit is True


def test_long_outcome_no_hit():
    # Entry at 100, exit at 99.8 → -0.2% < 0.5% threshold → no hit
    closes = [100.0, 100.5, 100.0, 99.8]
    df = _bars(closes)
    sig = _signal(df.index[0])
    out = _compute_outcome(sig, df, idx=0, direction="long",
                           horizon=3, threshold_pct=0.5)
    assert out is not None
    assert out.return_pct < 0.5
    assert out.hit is False


def test_short_outcome_hit():
    # Entry 100, drops to 98 → -2% in long terms = +2% favourable for short → hit
    closes = [100.0, 99.0, 98.0, 98.0]
    df = _bars(closes)
    sig = _signal(df.index[0])
    out = _compute_outcome(sig, df, idx=0, direction="short",
                           horizon=3, threshold_pct=0.5)
    assert out is not None
    assert out.return_pct == pytest.approx(-2.0)
    assert out.hit is True
    # MFE is in short's favour (entry - min_low) / entry * 100
    assert out.mfe_pct == pytest.approx(2.5)   # low reaches 97.5


def test_short_outcome_no_hit_when_price_rises():
    closes = [100.0, 100.5, 101.0, 101.0]
    df = _bars(closes)
    sig = _signal(df.index[0])
    out = _compute_outcome(sig, df, idx=0, direction="short",
                           horizon=3, threshold_pct=0.5)
    assert out is not None
    assert out.hit is False


def test_outcome_returns_none_when_no_forward_bars():
    closes = [100.0, 101.0, 102.0]
    df = _bars(closes)
    sig = _signal(df.index[2])
    # idx=2 is the last bar; horizon=3 → no forward bars
    assert _compute_outcome(sig, df, idx=2, direction="long",
                            horizon=3, threshold_pct=0.5) is None


# ---------------------------------------------------------------------------
# _infer_direction
# ---------------------------------------------------------------------------

def test_infer_direction_bb_lower_is_long():
    rule = BbReversalRule(name="x", timeframe="5m", side="lower")
    assert _infer_direction(rule) == "long"


def test_infer_direction_bb_upper_is_short():
    rule = BbReversalRule(name="x", timeframe="5m", side="upper")
    assert _infer_direction(rule) == "short"


def test_infer_direction_ma_up_is_long():
    rule = MaCrossReversalRule(name="x", timeframe="5m",
                                short=5, long=20, direction="up")
    assert _infer_direction(rule) == "long"


def test_infer_direction_ma_down_is_short():
    rule = MaCrossReversalRule(name="x", timeframe="5m",
                                short=5, long=20, direction="down")
    assert _infer_direction(rule) == "short"


def test_infer_direction_range_up_is_long():
    rule = RangeBreakoutRule(name="x", timeframe="15m", period=20, direction="up")
    assert _infer_direction(rule) == "long"


def test_infer_direction_range_down_is_short():
    rule = RangeBreakoutRule(name="x", timeframe="15m", period=20, direction="down")
    assert _infer_direction(rule) == "short"


def test_infer_direction_default_when_missing():
    class _NoExpected(Rule):
        @property
        def name(self): return "x"
        @property
        def timeframe(self): return "5m"
        def evaluate(self, symbol, bars): return None
    assert _infer_direction(_NoExpected()) == "long"


# ---------------------------------------------------------------------------
# BacktestResult aggregation
# ---------------------------------------------------------------------------

def test_result_aggregation():
    sig = _signal(datetime(2024, 1, 2, 10, 0, tzinfo=_TZ))
    outcomes = [
        TradeOutcome(sig, "long", 5, 100, 102, 2.0, 2.5, -0.5, True),
        TradeOutcome(sig, "long", 5, 100,  99, -1.0, 1.0, -1.5, False),
        TradeOutcome(sig, "long", 5, 100, 103, 3.0, 3.5,  0.0, True),
    ]
    result = BacktestResult(
        rule_name="r", timeframe="5m", direction="long",
        horizon_bars=5, hit_threshold_pct=0.5, outcomes=outcomes,
    )
    assert result.n_signals == 3
    assert result.n_hits == 2
    assert result.win_rate == pytest.approx(2 / 3)
    assert result.avg_return_pct == pytest.approx((2.0 - 1.0 + 3.0) / 3)
    assert result.avg_mfe_pct == pytest.approx((2.5 + 1.0 + 3.5) / 3)
    assert result.avg_mae_pct == pytest.approx((-0.5 - 1.5 + 0.0) / 3)


def test_result_empty_safe():
    result = BacktestResult(
        rule_name="r", timeframe="5m", direction="long",
        horizon_bars=5, hit_threshold_pct=0.5,
    )
    assert result.n_signals == 0
    assert result.win_rate == 0.0
    assert result.avg_return_pct == 0.0
    assert "no signals" in result.summary_row()


def test_summary_row_format_with_signals():
    sig = _signal(datetime(2024, 1, 2, 10, 0, tzinfo=_TZ))
    result = BacktestResult(
        rule_name="bb_reversal_5m", timeframe="5m", direction="long",
        horizon_bars=5, hit_threshold_pct=0.5,
        outcomes=[TradeOutcome(sig, "long", 5, 100, 102, 2.0, 2.5, -0.5, True)],
    )
    line = result.summary_row()
    assert "bb_reversal_5m" in line
    assert "n=  1" in line
    assert "win=100.0%" in line


# ---------------------------------------------------------------------------
# backtest_rule end-to-end with mock history
# ---------------------------------------------------------------------------

def test_backtest_rule_with_mock_history():
    from monitor.data.mock import make_mock_history
    hist = make_mock_history(["2330"], n_days=20, seed=0)

    rule = BbReversalRule(name="bb_reversal_5m", timeframe="5m", side="lower")
    result = backtest_rule(rule, ["2330"], hist, horizon=5, hit_threshold_pct=0.5)

    assert result.rule_name == "bb_reversal_5m"
    assert result.direction == "long"
    assert result.timeframe == "5m"
    assert isinstance(result.outcomes, list)
    # Don't assert exact count (mock data dependent), just shape
    assert all(o.horizon_bars == 5 for o in result.outcomes)
    assert all(o.direction == "long" for o in result.outcomes)


def test_backtest_rule_empty_history_returns_empty_result():
    rule = BbReversalRule(name="bb_reversal_5m", timeframe="5m", side="lower")
    result = backtest_rule(rule, ["2330"], {}, horizon=5)
    assert result.n_signals == 0


# ---------------------------------------------------------------------------
# backtest_yaml
# ---------------------------------------------------------------------------

def test_backtest_yaml_includes_disabled_by_default(tmp_path):
    from monitor.data.mock import make_mock_history

    yaml_content = """
- name: bb_reversal_5m
  enabled: true
  timeframe: 5m
  side: lower
- name: bb_reversal_upper_5m
  enabled: false
  timeframe: 5m
  side: upper
"""
    yaml_file = tmp_path / "rules.yaml"
    yaml_file.write_text(yaml_content)

    hist = make_mock_history(["2330"], n_days=20, seed=0)
    results = backtest_yaml(yaml_file, ["2330"], hist, horizon=5)

    rule_names = {r.rule_name for r in results}
    assert rule_names == {"bb_reversal_5m", "bb_reversal_upper_5m"}


def test_backtest_yaml_enabled_only(tmp_path):
    from monitor.data.mock import make_mock_history

    yaml_content = """
- name: bb_reversal_5m
  enabled: true
  timeframe: 5m
  side: lower
- name: bb_reversal_upper_5m
  enabled: false
  timeframe: 5m
  side: upper
"""
    yaml_file = tmp_path / "rules.yaml"
    yaml_file.write_text(yaml_content)

    hist = make_mock_history(["2330"], n_days=20, seed=0)
    results = backtest_yaml(yaml_file, ["2330"], hist,
                            horizon=5, include_disabled=False)
    assert {r.rule_name for r in results} == {"bb_reversal_5m"}
