from __future__ import annotations

import collections
from datetime import date, datetime

import pandas as pd
from loguru import logger

from monitor.data.historical import TIMEFRAMES, resample_bars

# Minutes covered by each closed timeframe boundary (intraday only).
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
        # One-time WARNING flag per symbol when we defer pending creation
        # because the broker has yet to ship a positive cumulative volume.
        self._deferred_warned: set[str] = set()

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
            # Defer: until the broker ships a positive cumulative volume
            # (IB ticker.volume often arrives as -1/NaN for the first few
            # ticks after subscribe), prev_volume would be 0 and the next
            # minute's bar would absorb the entire day's cumulative as one
            # outlier — poisoning vol_avg in every volume-gated rule for
            # the next ~window/4 hours.
            if total_volume <= 0:
                if symbol not in self._deferred_warned:
                    self._deferred_warned.add(symbol)
                    logger.warning(
                        "{}: deferring 1m bar build — broker reported "
                        "non-positive cumulative volume ({}). Will retry on "
                        "next snapshot. Verify broker live-data subscription "
                        "if this persists.",
                        symbol, total_volume,
                    )
                return closed
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

        # New minute started → close the 1-min bar.
        # Ratchet: a transient broker glitch can make total_volume regress
        # below pending["prev_volume"] (max(0, ...) clamps the bar to 0),
        # but we must NOT propagate the regressed value forward as the new
        # baseline — the next real reading would balloon bar_vol. Use
        # max(prev, current) so the next bar's delta stays sensible.
        latest_total = max(int(total_volume), int(pending["prev_volume"]))
        bar_vol = max(0, latest_total - pending["prev_volume"])
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

        # resample_bars uses label='right', closed='right' for intraday,
        # so the 09:05 5-min bar spans 1-min bars 09:01..09:05.
        bar_min = pending["ts"].minute
        for tf, tf_min in _TF_MINUTES.items():
            if tf == "1m":
                continue
            if bar_min % tf_min != 0:
                continue
            window_1m = list(self._bars[symbol]["1m"])[-tf_min:]
            if len(window_1m) < tf_min:
                continue
            df_slice = pd.DataFrame(window_1m)
            resampled = resample_bars(df_slice, f"{tf_min}min")
            if resampled.empty:
                continue
            self._bars[symbol][tf].append(resampled.iloc[-1])
            closed.append(tf)

        # Reset pending bar (use new tick's price; previous bar already
        # appended to the 1m deque above). prev_volume uses the ratcheted
        # latest_total so a transient zero/regression doesn't reset the
        # cumulative-volume baseline.
        self._pending[symbol] = {
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "prev_volume": latest_total,
            "bar_volume": 0,
            "ts": ts,
        }

        # Daily timeframe — rebuild today's bar from today's closed 1-min
        # bars + the just-reset pending bar, so daily.close always tracks
        # the latest tick (per Plan §7.2 daily exception).
        if "1d" in self._bars.get(symbol, {}):
            if self._update_daily_bar(symbol, ts):
                closed.append("1d")

        if closed:
            logger.debug("{}: closed bars {}", symbol, closed)

        return closed

    def symbols(self) -> list[str]:
        return list(self._bars.keys())

    # ------------------------------------------------------------------
    # Daily bar maintenance
    # ------------------------------------------------------------------

    def _update_daily_bar(self, symbol: str, ts: datetime) -> bool:
        """Rebuild today's daily bar from today's closed 1-min bars + the
        currently-open pending bar.

        Including the pending bar means today's daily.close tracks the
        latest tick rather than lagging by one minute, which is what
        intraday daily-rule evaluation needs.

        Returns True if today's bar was added/updated.
        """
        daily_dq = self._bars[symbol].get("1d")
        if daily_dq is None:
            return False

        today: date = ts.date()
        today_1m = [b for b in self._bars[symbol]["1m"]
                    if _bar_date(b) == today]
        pending = self._pending.get(symbol)
        has_pending_today = (pending is not None
                             and pending["ts"].date() == today)

        if not today_1m and not has_pending_today:
            return False

        opens: list[float] = []
        highs: list[float] = []
        lows: list[float] = []
        last_close: float | None = None
        total_volume: int = 0

        for bar in today_1m:
            opens.append(float(bar["open"]))
            highs.append(float(bar["high"]))
            lows.append(float(bar["low"]))
            last_close = float(bar["close"])
            total_volume += int(bar["volume"])

        if has_pending_today:
            opens.append(float(pending["open"]))
            highs.append(float(pending["high"]))
            lows.append(float(pending["low"]))
            last_close = float(pending["close"])  # latest tick wins
            # pending bar's volume isn't finalised yet; skip aggregation
            # so daily volume doesn't double-count the in-progress minute.

        agg = pd.Series(
            {
                "open": opens[0],
                "high": max(highs),
                "low": min(lows),
                "close": last_close,
                "volume": total_volume,
            },
            name=(pd.Timestamp(today, tz=ts.tzinfo)
                  if ts.tzinfo else pd.Timestamp(today)),
        )

        if daily_dq and _bar_date(daily_dq[-1]) == today:
            daily_dq[-1] = agg
        else:
            daily_dq.append(agg)
        return True


def _bar_date(bar: pd.Series) -> date | None:
    """Extract the date from a bar's index (Series.name) — handles both
    pandas Timestamp and stdlib datetime / date."""
    name = bar.name
    if name is None:
        return None
    if hasattr(name, "date"):
        d = name.date()
        return d if isinstance(d, date) else None
    if isinstance(name, date):
        return name
    return None
