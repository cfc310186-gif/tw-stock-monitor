from __future__ import annotations

import pandas as pd

from monitor.rules.base import Rule, Signal


class RangeBreakoutRule(Rule):
    """N-bar range breakout (Donchian-style).

    The channel is computed from the prior N bars (excluding the current bar
    so the test isn't self-referential):
      direction=up   突破: cur close > max(high) of prior N bars
      direction=down 跌破: cur close < min(low)  of prior N bars

    Signal fires only on the FIRST bar that breaks; while close stays beyond
    the level, no further trigger occurs (per-rule cooldown still applies on
    top of that).
    """

    def __init__(
        self,
        name: str,
        timeframe: str,
        period: int = 20,
        direction: str = "up",
        cooldown_minutes: int = 30,
    ) -> None:
        if direction not in ("up", "down"):
            raise ValueError(f"direction must be 'up' or 'down', got {direction!r}")
        if period < 2:
            raise ValueError(f"period must be >= 2, got {period}")
        self._name = name
        self._timeframe = timeframe
        self._period = period
        self._direction = direction
        self._cooldown = cooldown_minutes

    # -- Rule interface -------------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    @property
    def timeframe(self) -> str:
        return self._timeframe

    @property
    def cooldown_minutes(self) -> int:
        return self._cooldown

    @classmethod
    def from_config(cls, cfg: dict) -> "RangeBreakoutRule":
        return cls(
            name=cfg["name"],
            timeframe=cfg.get("timeframe", "15m"),
            period=cfg.get("period", 20),
            direction=cfg.get("direction", "up"),
            cooldown_minutes=cfg.get("cooldown_minutes", 30),
        )

    # -- Evaluation -----------------------------------------------------------

    def evaluate(self, symbol: str, bars: pd.DataFrame) -> Signal | None:
        if len(bars) < self._period + 2:
            return None

        prior_for_cur = bars.iloc[-(self._period + 1):-1]
        prior_for_prev = bars.iloc[-(self._period + 2):-2]
        cur_bar = bars.iloc[-1]
        prev_bar = bars.iloc[-2]

        if self._direction == "up":
            level = float(prior_for_cur["high"].max())
            level_prev = float(prior_for_prev["high"].max())
            broken_now = cur_bar["close"] > level
            was_broken_prev = prev_bar["close"] > level_prev
        else:
            level = float(prior_for_cur["low"].min())
            level_prev = float(prior_for_prev["low"].min())
            broken_now = cur_bar["close"] < level
            was_broken_prev = prev_bar["close"] < level_prev

        if not broken_now or was_broken_prev:
            return None

        return self._build_signal(symbol, bars, cur_bar, level)

    def _build_signal(
        self,
        symbol: str,
        bars: pd.DataFrame,
        cur_bar: pd.Series,
        level: float,
    ) -> Signal:
        bar_time = bars.index[-1]
        ts_str = bar_time.strftime("%H:%M") if hasattr(bar_time, "strftime") else str(bar_time)

        emoji = "🚀" if self._direction == "up" else "💥"
        verb = "突破" if self._direction == "up" else "跌破"
        edge_label = f"{self._period}根{'高' if self._direction == 'up' else '低'}"

        vol_avg = bars["volume"].iloc[-21:-1].mean()
        vol_ratio = float(cur_bar["volume"] / vol_avg) if vol_avg and vol_avg > 0 else 0.0

        message = (
            f"{emoji} {self._name} 觸發\n"
            f"{symbol} {self._timeframe} @ {ts_str}\n"
            f"收盤 {cur_bar['close']:.2f} {verb} {edge_label} {level:.2f}\n"
            f"量 {int(cur_bar['volume']):,} 張（量比 {vol_ratio:.1f}x）"
        )
        return Signal(
            symbol=symbol,
            rule_name=self._name,
            timeframe=self._timeframe,
            bar_close_time=bar_time,
            message=message,
            details={
                "close": float(cur_bar["close"]),
                "level": level,
                "volume": int(cur_bar["volume"]),
                "vol_ratio": round(vol_ratio, 2),
            },
        )
