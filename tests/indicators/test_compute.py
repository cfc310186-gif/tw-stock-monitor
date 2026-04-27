import math

import pandas as pd
import pytest

from monitor.indicators.compute import compute_last


def _make_df(n: int, price: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range("2024-01-02 09:01", periods=n, freq="1min", tz="Asia/Taipei", name="ts")
    return pd.DataFrame(
        {
            "open": [price] * n,
            "high": [price + 1] * n,
            "low": [price - 1] * n,
            "close": [price] * n,
            "volume": [1000] * n,
        },
        index=idx,
    )


def test_returns_none_when_insufficient():
    df = _make_df(25)  # need 26
    assert compute_last(df) is None


def test_returns_dict_with_all_keys():
    df = _make_df(60)
    result = compute_last(df)
    assert result is not None
    expected_keys = {
        "close", "volume", "ma5", "ma20",
        "bb_upper", "bb_middle", "bb_lower",
        "kd_k", "kd_d",
        "macd_dif", "macd_dem", "macd_osc",
        "atr14",
    }
    assert expected_keys.issubset(result.keys())


def test_constant_price_ma_equals_price():
    df = _make_df(60, price=200.0)
    result = compute_last(df)
    assert result is not None
    assert result["ma5"] == 200.0
    assert result["ma20"] == 200.0


def test_constant_price_bb_bands_equal():
    df = _make_df(60, price=150.0)
    result = compute_last(df)
    assert result is not None
    # Constant close → std=0 → all BB bands equal close
    assert result["bb_upper"] == result["bb_middle"] == result["bb_lower"] == 150.0


def test_values_are_floats_or_none():
    df = _make_df(60)
    result = compute_last(df)
    assert result is not None
    for k, v in result.items():
        if k == "volume":
            assert isinstance(v, int)
        else:
            assert v is None or isinstance(v, float)
