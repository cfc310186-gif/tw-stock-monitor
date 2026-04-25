from __future__ import annotations

import pandas as pd

from monitor.indicators.ma import sma


def bbands(close: pd.Series, period: int = 20, stddev: float = 2.0) -> pd.DataFrame:
    middle = sma(close, period)
    std = close.rolling(window=period, min_periods=period).std(ddof=0)
    upper = middle + stddev * std
    lower = middle - stddev * std
    return pd.DataFrame({"upper": upper, "middle": middle, "lower": lower})
