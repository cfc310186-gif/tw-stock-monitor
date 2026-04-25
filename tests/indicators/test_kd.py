import math

import pandas as pd

from monitor.indicators.kd import kd


def test_kd_warmup_nan():
    n = 12
    high = pd.Series(range(1, n + 1), dtype=float)
    low = pd.Series(range(0, n), dtype=float)
    close = (high + low) / 2
    out = kd(high, low, close, period=9)
    # First (period - 1) bars must be NaN
    for i in range(8):
        assert math.isnan(out["k"].iloc[i])
        assert math.isnan(out["d"].iloc[i])
    assert not math.isnan(out["k"].iloc[8])


def test_kd_constant_at_high():
    # Close always at the highest of the lookback window → RSV = 100 every bar
    high = pd.Series([10.0] * 20)
    low = pd.Series([0.0] * 20)
    close = pd.Series([10.0] * 20)
    out = kd(high, low, close, period=9)
    # K converges toward 100 as 1/3 weight pulls from prev_k=50 → 83.3 → 94.4 → ...
    assert out["k"].iloc[-1] > 99
    assert out["d"].iloc[-1] > 95


def test_kd_constant_at_low():
    high = pd.Series([10.0] * 20)
    low = pd.Series([0.0] * 20)
    close = pd.Series([0.0] * 20)
    out = kd(high, low, close, period=9)
    # K converges toward 0
    assert out["k"].iloc[-1] < 1
    assert out["d"].iloc[-1] < 5


def test_kd_first_value_formula():
    # Verify first computed K/D with a controlled RSV at position 8 (period=9)
    high = pd.Series([2.0] * 9)
    low = pd.Series([0.0] * 9)
    close = pd.Series([1.0] * 9)
    out = kd(high, low, close, period=9)
    # At i=8: lowest=0, highest=2, close=1 → RSV=50
    # K = 2/3 * 50 + 1/3 * 50 = 50
    # D = 2/3 * 50 + 1/3 * 50 = 50
    assert abs(out["k"].iloc[8] - 50.0) < 1e-9
    assert abs(out["d"].iloc[8] - 50.0) < 1e-9
