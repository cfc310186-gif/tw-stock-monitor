import math

import pandas as pd

from monitor.indicators.macd import macd


def test_macd_constant_input():
    s = pd.Series([10.0] * 50)
    out = macd(s, fast=12, slow=26, signal=9)
    # Constant input: DIF=0, DEM=0, OSC=0
    assert out["dif"].iloc[-1] == 0.0
    assert out["dem"].iloc[-1] == 0.0
    assert out["osc"].iloc[-1] == 0.0


def test_macd_warmup_nan():
    s = pd.Series(range(1, 50), dtype=float)
    out = macd(s, fast=12, slow=26, signal=9)
    # DIF needs slow=26 bars; DEM needs slow + signal - 1 = 34 bars
    assert math.isnan(out["dif"].iloc[24])
    assert not math.isnan(out["dif"].iloc[25])
    assert math.isnan(out["dem"].iloc[32])
    assert not math.isnan(out["dem"].iloc[33])


def test_macd_columns():
    s = pd.Series(range(1, 50), dtype=float)
    out = macd(s)
    assert list(out.columns) == ["dif", "dem", "osc"]


def test_macd_osc_sign_uptrend():
    # Strong uptrend → DIF should be positive at the end
    s = pd.Series([float(i) for i in range(1, 60)])
    out = macd(s)
    assert out["dif"].iloc[-1] > 0
