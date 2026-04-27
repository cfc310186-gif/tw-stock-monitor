import math

import pandas as pd

from monitor.indicators.bbands import bbands


def test_bbands_constant_input():
    s = pd.Series([10.0] * 25)
    out = bbands(s, period=20, stddev=2.0)
    # Constant data → std=0 → upper=middle=lower=10
    assert out["middle"].iloc[-1] == 10.0
    assert out["upper"].iloc[-1] == 10.0
    assert out["lower"].iloc[-1] == 10.0


def test_bbands_warmup_nan():
    s = pd.Series(range(1, 30), dtype=float)
    out = bbands(s, period=20, stddev=2.0)
    for i in range(19):
        assert math.isnan(out["middle"].iloc[i])
    assert not math.isnan(out["middle"].iloc[19])


def test_bbands_columns():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    out = bbands(s, period=3, stddev=2.0)
    assert list(out.columns) == ["upper", "middle", "lower"]
    # period=3, stddev=2: window [3,4,5], mean=4, pop_std=sqrt(2/3)=0.8165
    assert out["middle"].iloc[-1] == 4.0
    expected_std = (2 / 3) ** 0.5
    assert abs(out["upper"].iloc[-1] - (4.0 + 2 * expected_std)) < 1e-9
    assert abs(out["lower"].iloc[-1] - (4.0 - 2 * expected_std)) < 1e-9
