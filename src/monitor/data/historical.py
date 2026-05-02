from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

import pandas as pd
from loguru import logger

from monitor.instruments import InstrumentType

if TYPE_CHECKING:
    from monitor.broker.shioaji_client import ShioajiClient

# Timeframe name → pandas resample rule (None = keep 1-min as-is).
# "1d" uses calendar-day boundaries — labels each daily bar at 00:00 of
# that date (label="left", closed="left") so the bar timestamp matches
# the trading day intuitively.
TIMEFRAMES: dict[str, str | None] = {
    "1m": None,
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "60m": "60min",
    "1d": "1D",
}

OHLCV_AGG = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}


MAX_LOOKBACK_DAYS_BY_TYPE: dict[InstrumentType, int] = {
    InstrumentType.OVERSEAS_FUTURES: 5,
}


def _effective_lookback_days(itype: InstrumentType, requested_days: int) -> int:
    max_days = MAX_LOOKBACK_DAYS_BY_TYPE.get(itype)
    if max_days is None:
        return requested_days
    return min(requested_days, max_days)


def resample_bars(df_1m: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample a 1-min OHLCV DataFrame to a coarser timeframe.

    For intraday bars (5min … 60min) we use label='right', closed='right'
    so the bar at 09:05 contains 09:01–09:05 — matches the TW broker
    convention. For daily bars we use label='left', closed='left' so the
    bar at 2024-01-02 00:00 represents trading on 2024-01-02.
    Rows with no trades (NaN close) are dropped.
    """
    is_daily = rule.upper() in ("1D", "D")
    label = "left" if is_daily else "right"
    closed = "left" if is_daily else "right"
    return (
        df_1m.resample(rule, label=label, closed=closed)
        .agg(OHLCV_AGG)
        .dropna(subset=["close"])
    )


def load_history(
    client: "ShioajiClient",
    instruments: dict[str, InstrumentType] | list[str],
    lookback_days: int = 60,
) -> dict[str, dict[str, pd.DataFrame]]:
    """Bootstrap historical K bars for all symbols and timeframes.

    `instruments` is preferably a {symbol: InstrumentType} mapping. Passing
    a plain list of symbols is also accepted (treated as all stocks) for
    backwards compatibility with older callers / tests.
    """
    if isinstance(instruments, list):
        instruments = {s: InstrumentType.STOCK for s in instruments}

    end = date.today()
    result: dict[str, dict[str, pd.DataFrame]] = {}

    for sym, itype in instruments.items():
        effective_lookback_days = _effective_lookback_days(itype, lookback_days)
        start = end - timedelta(days=effective_lookback_days)
        if effective_lookback_days != lookback_days:
            logger.info(
                "Capping history lookback for {} [{}]: {} -> {} day(s)",
                sym,
                itype.value,
                lookback_days,
                effective_lookback_days,
            )
        logger.info("Loading history for {} [{}] ({} → {})",
                    sym, itype.value, start, end)
        try:
            df_1m = client.kbars(sym, itype, start=start, end=end)
        except NotImplementedError as exc:
            logger.warning("Skipping {}: {}", sym, exc)
            continue
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
