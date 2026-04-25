from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

import pandas as pd
from loguru import logger

if TYPE_CHECKING:
    from monitor.broker.shioaji_client import ShioajiClient

# Timeframe name → pandas resample rule (None = keep 1-min as-is)
TIMEFRAMES: dict[str, str | None] = {
    "1m": None,
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "60m": "60min",
}

OHLCV_AGG = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}


def resample_bars(df_1m: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample a 1-min OHLCV DataFrame to a coarser timeframe.

    label='right', closed='right': bar at 09:05 contains 09:01–09:05.
    Rows with no trades (NaN close) are dropped.
    """
    return (
        df_1m.resample(rule, label="right", closed="right")
        .agg(OHLCV_AGG)
        .dropna(subset=["close"])
    )


def load_history(
    client: "ShioajiClient",
    symbols: list[str],
    lookback_days: int = 60,
) -> dict[str, dict[str, pd.DataFrame]]:
    """Bootstrap historical K bars for all symbols and timeframes.

    Returns ``{symbol: {timeframe: DataFrame}}``.
    Missing or empty symbols are skipped with a warning.
    """
    end = date.today()
    start = end - timedelta(days=lookback_days)
    result: dict[str, dict[str, pd.DataFrame]] = {}

    for sym in symbols:
        logger.info("Loading history for {} ({} → {})", sym, start, end)
        try:
            df_1m = client.kbars(sym, start=start, end=end)
        except Exception as exc:
            logger.warning("kbars failed for {}: {}", sym, exc)
            continue

        if df_1m.empty:
            logger.warning("No data for {} — skipped", sym)
            continue

        frames: dict[str, pd.DataFrame] = {"1m": df_1m}
        for tf, rule in TIMEFRAMES.items():
            if rule is not None:
                frames[tf] = resample_bars(df_1m, rule)

        result[sym] = frames
        logger.info(
            "{}: {} 1-min bars, {} trading days",
            sym,
            len(df_1m),
            df_1m.index.normalize().nunique(),
        )

    return result
