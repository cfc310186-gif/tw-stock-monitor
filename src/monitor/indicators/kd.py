from __future__ import annotations

import numpy as np
import pandas as pd


def kd(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 9,
) -> pd.DataFrame:
    """Taiwan-style smoothed Stochastic (KD).

    K(t) = 2/3 * K(t-1) + 1/3 * RSV(t)
    D(t) = 2/3 * D(t-1) + 1/3 * K(t)

    Initial K and D both start at 50.
    """
    lowest = low.rolling(window=period, min_periods=period).min()
    highest = high.rolling(window=period, min_periods=period).max()
    rng = highest - lowest
    rsv = (close - lowest) / rng.replace(0, np.nan) * 100

    k_values = np.full(len(close), np.nan)
    d_values = np.full(len(close), np.nan)

    prev_k, prev_d = 50.0, 50.0
    started = False
    for i, r in enumerate(rsv.to_numpy()):
        if np.isnan(r):
            if started:
                k_values[i] = prev_k
                d_values[i] = prev_d
            continue
        cur_k = (2 / 3) * prev_k + (1 / 3) * r
        cur_d = (2 / 3) * prev_d + (1 / 3) * cur_k
        k_values[i] = cur_k
        d_values[i] = cur_d
        prev_k, prev_d = cur_k, cur_d
        started = True

    return pd.DataFrame(
        {"k": k_values, "d": d_values},
        index=close.index,
    )
