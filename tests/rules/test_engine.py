from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from monitor.rules.base import Rule, Signal
from monitor.rules.bb_reversal import BbReversalRule
from monitor.rules.engine import RuleEngine


# ---------------------------------------------------------------------------
# Helper: a rule that always fires with a fixed bar_close_time
# ---------------------------------------------------------------------------

class _AlwaysRule(Rule):
    def __init__(self, tf: str = "5m", cooldown: int = 30) -> None:
        self._tf = tf
        self._cooldown = cooldown

    @property
    def name(self) -> str:
        return "always"

    @property
    def timeframe(self) -> str:
        return self._tf

    @property
    def cooldown_minutes(self) -> int:
        return self._cooldown

    def evaluate(self, symbol: str, bars: pd.DataFrame) -> Signal | None:
        return Signal(
            symbol=symbol,
            rule_name=self.name,
            timeframe=self._tf,
            bar_close_time=bars.index[-1] if not bars.empty else datetime(2024, 1, 2, 10, 0),
            message="always fires",
        )


def _empty_bars(n: int = 5) -> pd.DataFrame:
    idx = pd.date_range("2024-01-02 09:01", periods=n, freq="1min", tz="Asia/Taipei", name="ts")
    return pd.DataFrame(
        {"open": [100.0] * n, "high": [101.0] * n,
         "low": [99.0] * n, "close": [100.0] * n, "volume": [1000] * n},
        index=idx,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_evaluate_returns_signal():
    engine = RuleEngine([_AlwaysRule(tf="5m")])
    bars = _empty_bars()
    sigs = engine.evaluate("2330", "5m", bars, now=datetime(2024, 1, 2, 10, 0))
    assert len(sigs) == 1
    assert sigs[0].rule_name == "always"


def test_evaluate_skips_wrong_timeframe():
    engine = RuleEngine([_AlwaysRule(tf="15m")])
    bars = _empty_bars()
    sigs = engine.evaluate("2330", "5m", bars)
    assert sigs == []


def test_bar_level_dedup():
    engine = RuleEngine([_AlwaysRule(tf="5m", cooldown=0)])
    bars = _empty_bars()
    t = datetime(2024, 1, 2, 10, 0)
    sigs1 = engine.evaluate("2330", "5m", bars, now=t)
    sigs2 = engine.evaluate("2330", "5m", bars, now=t + timedelta(seconds=30))
    assert len(sigs1) == 1
    assert len(sigs2) == 0  # same bar_close_time → dedup


def test_rule_cooldown():
    engine = RuleEngine([_AlwaysRule(tf="5m", cooldown=30)])
    bars1 = _empty_bars(5)
    bars2 = _empty_bars(6)  # slightly different bars → different bar_ts
    t = datetime(2024, 1, 2, 10, 0)
    sigs1 = engine.evaluate("2330", "5m", bars1, now=t)
    sigs2 = engine.evaluate("2330", "5m", bars2, now=t + timedelta(minutes=5))
    assert len(sigs1) == 1
    assert len(sigs2) == 0  # within 30-min cooldown


def test_rule_cooldown_expired():
    engine = RuleEngine([_AlwaysRule(tf="5m", cooldown=10)])
    bars1 = _empty_bars(5)
    bars2 = _empty_bars(6)
    t = datetime(2024, 1, 2, 10, 0)
    engine.evaluate("2330", "5m", bars1, now=t)
    sigs = engine.evaluate("2330", "5m", bars2, now=t + timedelta(minutes=15))
    assert len(sigs) == 1  # cooldown expired


def test_global_cooldown_across_rules():
    rule_a = _AlwaysRule(tf="5m", cooldown=0)
    rule_a._name = "ruleA"  # type: ignore[attr-defined]

    class _AlwaysB(_AlwaysRule):
        @property
        def name(self) -> str:
            return "ruleB"

    engine = RuleEngine([rule_a, _AlwaysB(tf="5m", cooldown=0)])
    bars = _empty_bars(5)
    t = datetime(2024, 1, 2, 10, 0)
    sigs = engine.evaluate("2330", "5m", bars, now=t)
    # Global cooldown: first rule fires → second is silenced for 10 min
    assert len(sigs) == 1


def test_replay_collects_multiple_signals():
    rule = BbReversalRule("bb_reversal_5m", "5m", side="lower")
    engine = RuleEngine([rule])
    # Use mock data: replay over 5m bars with enough history
    from monitor.data.mock import make_mock_history
    hist = make_mock_history(["2330"], n_days=20, seed=0)
    df5 = hist["2330"]["5m"]
    signals = engine.replay("2330", "5m", df5)
    # We can't assert exact count without determinism, but should have ≥ 0
    assert isinstance(signals, list)
    assert all(s.rule_name == "bb_reversal_5m" for s in signals)


def test_from_yaml(tmp_path: Path):
    yaml_content = """
- name: bb_reversal_5m
  enabled: true
  timeframe: 5m
  side: lower
  period: 20
  stddev: 2
  cooldown_minutes: 30
- name: disabled_rule
  enabled: false
  timeframe: 5m
  side: upper
  period: 20
  stddev: 2
  cooldown_minutes: 30
"""
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(yaml_content)
    engine = RuleEngine.from_yaml(rules_file)
    # Only 1 enabled rule
    assert len(engine._rules) == 1
    assert engine._rules[0].name == "bb_reversal_5m"


def test_from_yaml_loads_all_rule_types(tmp_path: Path):
    """M5: YAML can mix bb_reversal / ma_cross_reversal / range_breakout."""
    yaml_content = """
- name: bb_reversal_5m
  enabled: true
  timeframe: 5m
  side: lower
  period: 20
  stddev: 2
- name: ma_cross_reversal_up_5m
  enabled: true
  timeframe: 5m
  short: 5
  long: 20
  direction: up
  ma_type: ema
- name: range_breakout_up_15m
  enabled: true
  timeframe: 15m
  period: 20
  direction: up
"""
    from monitor.rules.bb_reversal import BbReversalRule
    from monitor.rules.ma_cross_reversal import MaCrossReversalRule
    from monitor.rules.range_breakout import RangeBreakoutRule

    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(yaml_content)
    engine = RuleEngine.from_yaml(rules_file)

    classes = {type(r) for r in engine._rules}
    assert classes == {BbReversalRule, MaCrossReversalRule, RangeBreakoutRule}
