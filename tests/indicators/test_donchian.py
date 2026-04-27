import math

import pandas as pd

from monitor.indicators.donchian import donchian


def test_donchian_basic():
    high = pd.Series([10, 12, 11, 14, 13, 15], dtype=float)
    low = pd.Series([8, 9, 9, 11, 10, 12], dtype=float)
    out = donchian(high, low, period=3)
    # i=0,1: NaN
    assert math.isnan(out["upper"].iloc[0])
    assert math.isnan(out["upper"].iloc[1])
    # i=2: max(10,12,11)=12, min(8,9,9)=8, mid=10
    assert out["upper"].iloc[2] == 12.0
    assert out["lower"].iloc[2] == 8.0
    assert out["middle"].iloc[2] == 10.0
    # i=5: max(14,13,15)=15, min(11,10,12)=10, mid=12.5
    assert out["upper"].iloc[5] == 15.0
    assert out["lower"].iloc[5] == 10.0
    assert out["middle"].iloc[5] == 12.5


def test_donchian_columns():
    high = pd.Series([1.0, 2.0, 3.0])
    low = pd.Series([0.0, 1.0, 2.0])
    out = donchian(high, low, period=2)
    assert list(out.columns) == ["upper", "middle", "lower"]
