from __future__ import annotations

import pandas as pd

from monitor.indicators.ma import ema


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """MACD (DIF, DEM, OSC).

    DIF = EMA(close, fast) - EMA(close, slow)
    DEM = EMA(DIF, signal)
    OSC = DIF - DEM
    """
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    dif = ema_fast - ema_slow
    dem = ema(dif.dropna(), signal).reindex(close.index)
    osc = dif - dem
    return pd.DataFrame({"dif": dif, "dem": dem, "osc": osc})
