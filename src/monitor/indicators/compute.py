from __future__ import annotations

import math

import pandas as pd

from monitor.indicators.atr import atr
from monitor.indicators.bbands import bbands
from monitor.indicators.kd import kd
from monitor.indicators.ma import sma
from monitor.indicators.macd import macd

_MIN_BARS = 26  # minimum bars needed for MACD(12,26,9)


def compute_last(df: pd.DataFrame) -> dict[str, float] | None:
    """Compute all indicators for a DataFrame and return the last-bar values.

    Returns None if there are insufficient bars.
    Each value is a plain float; NaN becomes None.
    """
    if len(df) < _MIN_BARS:
        return None

    def _f(val: float) -> float | None:
        return None if math.isnan(val) else round(float(val), 4)

    c, h, lo = df["close"], df["high"], df["low"]

    bb = bbands(c, 20, 2.0)
    kd_df = kd(h, lo, c, 9)
    macd_df = macd(c)

    return {
        "close": _f(c.iloc[-1]),
        "volume": int(df["volume"].iloc[-1]),
        "ma5": _f(sma(c, 5).iloc[-1]),
        "ma20": _f(sma(c, 20).iloc[-1]),
        "bb_upper": _f(bb["upper"].iloc[-1]),
        "bb_middle": _f(bb["middle"].iloc[-1]),
        "bb_lower": _f(bb["lower"].iloc[-1]),
        "kd_k": _f(kd_df["k"].iloc[-1]),
        "kd_d": _f(kd_df["d"].iloc[-1]),
        "macd_dif": _f(macd_df["dif"].iloc[-1]),
        "macd_dem": _f(macd_df["dem"].iloc[-1]),
        "macd_osc": _f(macd_df["osc"].iloc[-1]),
        "atr14": _f(atr(h, lo, c, 14).iloc[-1]),
    }
