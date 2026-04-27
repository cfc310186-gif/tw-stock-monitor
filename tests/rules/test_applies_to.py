"""Tests for per-instrument-type rule scoping (applies_to)."""
from __future__ import annotations

from pathlib import Path

import pytest

from monitor.instruments import InstrumentType
from monitor.rules.base import parse_applies_to
from monitor.rules.bb_reversal import BbReversalRule
from monitor.rules.engine import RuleEngine
from monitor.rules.ma_cross_reversal import MaCrossReversalRule
from monitor.rules.range_breakout import RangeBreakoutRule


# ---------------------------------------------------------------------------
# parse_applies_to
# ---------------------------------------------------------------------------

def test_parse_default_is_all_types():
    assert parse_applies_to({}) == set(InstrumentType)


def test_parse_single_string():
    assert parse_applies_to({"applies_to": "stock"}) == {InstrumentType.STOCK}


def test_parse_list():
    out = parse_applies_to({"applies_to": ["stock", "domestic_futures"]})
    assert out == {InstrumentType.STOCK, InstrumentType.DOMESTIC_FUTURES}


def test_parse_invalid_raises():
    with pytest.raises(ValueError, match="Invalid applies_to"):
        parse_applies_to({"applies_to": "crypto"})


# ---------------------------------------------------------------------------
# Per-rule applies_to property
# ---------------------------------------------------------------------------

def test_bb_reversal_applies_to_default_is_all():
    rule = BbReversalRule(name="x", timeframe="5m")
    assert rule.applies_to == set(InstrumentType)


def test_bb_reversal_applies_to_from_yaml():
    rule = BbReversalRule.from_config({
        "name": "bb_reversal_5m_dfut",
        "timeframe": "5m",
        "side": "lower",
        "min_volume_ratio": 1.2,
        "applies_to": "domestic_futures",
    })
    assert rule.applies_to == {InstrumentType.DOMESTIC_FUTURES}


def test_ma_cross_applies_to_from_yaml():
    rule = MaCrossReversalRule.from_config({
        "name": "ma_cross_reversal_up_5m_stock",
        "timeframe": "5m",
        "applies_to": ["stock"],
    })
    assert rule.applies_to == {InstrumentType.STOCK}


def test_range_breakout_applies_to_from_yaml():
    rule = RangeBreakoutRule.from_config({
        "name": "range_breakout_up_15m_ofut",
        "timeframe": "15m",
        "direction": "up",
        "applies_to": "overseas_futures",
    })
    assert rule.applies_to == {InstrumentType.OVERSEAS_FUTURES}


# ---------------------------------------------------------------------------
# Engine filters by applies_to when itype is supplied
# ---------------------------------------------------------------------------

class _AlwaysFire:
    def __init__(self, name, applies_to: set[InstrumentType]):
        self._name = name
        self._tf = "5m"
        self._applies_to = applies_to

    name = property(lambda self: self._name)
    timeframe = property(lambda self: self._tf)
    cooldown_minutes = 0
    applies_to = property(lambda self: self._applies_to)

    def evaluate(self, symbol, bars):
        from datetime import datetime
        from monitor.rules.base import Signal
        return Signal(symbol=symbol, rule_name=self._name, timeframe=self._tf,
                      bar_close_time=datetime(2024, 1, 2, 10, 0),
                      message="test")


def _bars():
    import pandas as pd
    idx = pd.date_range("2024-01-02 09:01", periods=5, freq="1min",
                        tz="Asia/Taipei", name="ts")
    return pd.DataFrame(
        {"open": [100.0]*5, "high": [101]*5, "low": [99]*5,
         "close": [100]*5, "volume": [1000]*5},
        index=idx,
    )


def test_engine_filters_by_itype():
    stock_rule = _AlwaysFire("stock_only", {InstrumentType.STOCK})
    dfut_rule = _AlwaysFire("dfut_only", {InstrumentType.DOMESTIC_FUTURES})
    engine = RuleEngine([stock_rule, dfut_rule])

    sigs = engine.evaluate("2330", "5m", _bars(), itype=InstrumentType.STOCK)
    assert [s.rule_name for s in sigs] == ["stock_only"]


def test_engine_returns_all_when_itype_omitted():
    """Backwards compat: callers that don't supply itype see every rule."""
    stock_rule = _AlwaysFire("a", {InstrumentType.STOCK})
    dfut_rule = _AlwaysFire("b", {InstrumentType.DOMESTIC_FUTURES})
    engine = RuleEngine([stock_rule, dfut_rule])
    sigs = engine.evaluate("2330", "5m", _bars())
    # global per-symbol cooldown silences the second one, but both are
    # evaluated; the first rule's signal must come through.
    assert any(s.rule_name == "a" for s in sigs)


# ---------------------------------------------------------------------------
# YAML round-trip: bundled rules.yaml loads cleanly with applies_to
# ---------------------------------------------------------------------------

def test_bundled_rules_yaml_loads_with_applies_to():
    rules_path = Path(__file__).resolve().parents[2] / "config" / "rules.yaml"
    engine = RuleEngine.from_yaml(rules_path, include_disabled=True)
    # Each loaded rule should have a non-empty applies_to.
    for rule in engine._rules:
        assert rule.applies_to, f"{rule.name} has empty applies_to"
