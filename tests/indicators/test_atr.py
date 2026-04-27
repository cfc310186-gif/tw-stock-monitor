import math

import pandas as pd

from monitor.indicators.atr import atr


def test_atr_constant_input():
    # Same OHLC every bar → TR=0 → ATR=0 once warmed up
    high = pd.Series([10.0] * 20)
    low = pd.Series([10.0] * 20)
    close = pd.Series([10.0] * 20)
    out = atr(high, low, close, period=14)
    assert out.iloc[-1] == 0.0


def test_atr_warmup_nan():
    high = pd.Series([float(i) + 1 for i in range(20)])
    low = pd.Series([float(i) for i in range(20)])
    close = pd.Series([float(i) + 0.5 for i in range(20)])
    out = atr(high, low, close, period=14)
    for i in range(13):
        assert math.isnan(out.iloc[i])
    assert not math.isnan(out.iloc[13])


def test_atr_positive_when_volatile():
    high = pd.Series([10.0, 12.0] * 15)
    low = pd.Series([8.0, 7.0] * 15)
    close = pd.Series([9.0, 11.0] * 15)
    out = atr(high, low, close, period=14)
    assert out.iloc[-1] > 0
