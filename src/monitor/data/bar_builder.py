from __future__ import annotations

import collections
from datetime import datetime

import pandas as pd
from loguru import logger

from monitor.data.historical import TIMEFRAMES, resample_bars

# Minutes covered by each closed timeframe boundary
_TF_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "60m": 60,
}


class BarBuilder:
    """Manages rolling OHLCV windows per symbol/timeframe.

    Usage:
        builder = BarBuilder(hist, window=200)
        # Each snapshot poll:
        closed = builder.on_snapshot(symbol, price, total_volume, ts)
        # closed → list of timeframe strings that just completed a bar
        bars_5m = builder.get_bars("2330", "5m")   # returns DataFrame
    """

    def __init__(
        self,
        hist: dict[str, dict[str, pd.DataFrame]],
        window: int = 200,
    ) -> None:
        self._window = window
        # {symbol: {timeframe: deque of Series}}
        self._bars: dict[str, dict[str, collections.deque]] = {}
        # {symbol: {"open":float, "high":float, "low":float, "prev_volume":int, "ts":datetime}}
        self._pending: dict[str, dict | None] = {}

        for sym, frames in hist.items():
            self._bars[sym] = {}
            for tf, df in frames.items():
                dq: collections.deque = collections.deque(maxlen=window)
                for _, row in df.iloc[-window:].iterrows():
                    dq.append(row)
                self._bars[sym][tf] = dq
            self._pending[sym] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_bars(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Return the rolling window as a DataFrame (oldest → newest)."""
        dq = self._bars.get(symbol, {}).get(timeframe)
        if not dq:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        return pd.DataFrame(list(dq))

    def on_snapshot(
        self,
        symbol: str,
        price: float,
        total_volume: int,
        ts: datetime,
    ) -> list[str]:
        """Feed a new snapshot; return timeframes with newly closed bars."""
        if symbol not in self._bars:
            self._bars[symbol] = {tf: collections.deque(maxlen=self._window) for tf in TIMEFRAMES}
            self._pending[symbol] = None

        pending = self._pending[symbol]
        closed: list[str] = []

        if pending is None:
            self._pending[symbol] = {
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "prev_volume": total_volume,
                "bar_volume": 0,
                "ts": ts,
            }
            return closed

        # Same 1-min bar: update in place
        if ts.replace(second=0, microsecond=0) == pending["ts"].replace(second=0, microsecond=0):
            pending["high"] = max(pending["high"], price)
            pending["low"] = min(pending["low"], price)
            pending["close"] = price
            return closed

        # New minute started → close the 1-min bar
        bar_vol = max(0, total_volume - pending["prev_volume"])
        closed_bar = pd.Series(
            {
                "open": pending["open"],
                "high": pending["high"],
                "low": pending["low"],
                "close": pending["close"],
                "volume": bar_vol,
            },
            name=pending["ts"].replace(second=0, microsecond=0),
        )

        # Append to 1-min window
        self._bars[symbol]["1m"].append(closed_bar)
        closed.append("1m")

        # Check each coarser timeframe
        for tf, tf_min in _TF_MINUTES.items():
            if tf == "1m":
                continue
            bar_min = pending["ts"].minute
            if bar_min % tf_min == tf_min - 1 or len(self._bars[symbol]["1m"]) >= tf_min:
                # Resample the last tf_min 1-min bars
                window_1m = list(self._bars[symbol]["1m"])[-tf_min:]
                if len(window_1m) == tf_min:
                    df_slice = pd.DataFrame(window_1m)
                    rule = f"{tf_min}min"
                    resampled = resample_bars(df_slice, rule)
                    if not resampled.empty:
                        self._bars[symbol][tf].append(resampled.iloc[-1])
                        closed.append(tf)

        # Reset pending bar
        self._pending[symbol] = {
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "prev_volume": total_volume,
            "bar_volume": 0,
            "ts": ts,
        }

        if closed:
            logger.debug("{}: closed bars {}", symbol, closed)

        return closed

    def symbols(self) -> list[str]:
        return list(self._bars.keys())
