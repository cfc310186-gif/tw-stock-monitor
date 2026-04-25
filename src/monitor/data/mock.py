from __future__ import annotations

import numpy as np
import pandas as pd

from monitor.data.historical import TIMEFRAMES, resample_bars

# Approximate reference prices for common watchlist symbols
_BASE_PRICES: dict[str, float] = {
    "2330": 900.0,
    "2317": 155.0,
    "2454": 820.0,
    "0050": 185.0,
    "2603": 48.0,
}
_DEFAULT_BASE = 100.0

_BARS_PER_DAY = 270          # 09:01–13:30 = 270 minutes
_DAILY_VOLATILITY = 0.015    # ±1.5 % intraday sigma


def make_mock_history(
    symbols: list[str],
    n_days: int = 30,
    seed: int = 42,
) -> dict[str, dict[str, pd.DataFrame]]:
    """Generate synthetic 1-min OHLCV bars and resample to all timeframes.

    Prices follow a geometric random walk within each day, reset each
    morning to a fresh starting point close to the previous close.
    """
    rng = np.random.default_rng(seed)
    result: dict[str, dict[str, pd.DataFrame]] = {}

    for sym in symbols:
        base = _BASE_PRICES.get(sym, _DEFAULT_BASE)
        rows, timestamps = _gen_1m(sym, base, n_days, _BARS_PER_DAY, rng)

        idx = pd.DatetimeIndex(timestamps, name="ts", tz="Asia/Taipei")
        df_1m = pd.DataFrame(rows, index=idx)

        frames: dict[str, pd.DataFrame] = {"1m": df_1m}
        for tf, rule in TIMEFRAMES.items():
            if rule is not None:
                frames[tf] = resample_bars(df_1m, rule)

        result[sym] = frames

    return result


def _gen_1m(
    sym: str,
    base: float,
    n_days: int,
    bars_per_day: int,
    rng: np.random.Generator,
) -> tuple[list[dict], list[pd.Timestamp]]:
    sigma = _DAILY_VOLATILITY / (bars_per_day ** 0.5)
    rows: list[dict] = []
    timestamps: list[pd.Timestamp] = []

    price = base
    for day in range(n_days):
        # Trading days only (Mon–Fri), offset back from today
        date = pd.Timestamp.now(tz="Asia/Taipei").normalize() - pd.Timedelta(days=n_days - day)
        if date.dayofweek >= 5:   # skip Saturday (5) and Sunday (6)
            continue

        # Gap at open: small overnight drift
        price *= (1 + rng.normal(0, 0.003))

        for m in range(bars_per_day):
            ts = date + pd.Timedelta(hours=9, minutes=1 + m)
            ret = rng.normal(0, sigma)
            close = max(price * (1 + ret), 0.1)
            high = max(price, close) * (1 + abs(rng.normal(0, sigma / 2)))
            low = min(price, close) * (1 - abs(rng.normal(0, sigma / 2)))
            vol = int(rng.integers(500, 5000))

            rows.append(
                {"open": round(price, 2), "high": round(high, 2),
                 "low": round(low, 2), "close": round(close, 2), "volume": vol}
            )
            timestamps.append(ts)
            price = close

    return rows, timestamps
