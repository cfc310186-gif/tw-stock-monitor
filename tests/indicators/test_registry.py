import pytest

from monitor.indicators.registry import INDICATORS, get


def test_registry_has_all_indicators():
    expected = {"sma", "ema", "bbands", "kd", "macd", "donchian", "atr"}
    assert expected.issubset(INDICATORS.keys())


def test_get_returns_callable():
    fn = get("sma")
    assert callable(fn)


def test_get_unknown_raises():
    with pytest.raises(KeyError):
        get("nonexistent")
