import math

import pandas as pd

from monitor.indicators.ma import ema, sma


def test_sma_basic():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    out = sma(s, period=3)
    assert math.isnan(out.iloc[0])
    assert math.isnan(out.iloc[1])
    assert out.iloc[2] == 2.0  # (1+2+3)/3
    assert out.iloc[3] == 3.0
    assert out.iloc[4] == 4.0


def test_sma_period_longer_than_series():
    s = pd.Series([1, 2, 3], dtype=float)
    out = sma(s, period=5)
    assert out.isna().all()


def test_ema_basic():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    out = ema(s, period=3)
    # alpha = 2/(3+1) = 0.5
    # First value (period=3): SMA-like seed via pandas adjust=False starts at index 0,
    # but min_periods=3 leaves first 2 NaN.
    assert math.isnan(out.iloc[0])
    assert math.isnan(out.iloc[1])
    # ewm with adjust=False: y0=x0=1, y1=0.5*2+0.5*1=1.5, y2=0.5*3+0.5*1.5=2.25
    assert out.iloc[2] == 2.25


def test_ema_alpha_consistency():
    s = pd.Series([10.0] * 10)
    out = ema(s, period=3)
    # Constant input should converge to constant output
    assert out.iloc[-1] == 10.0
