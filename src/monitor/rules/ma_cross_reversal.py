from __future__ import annotations

import pandas as pd

from monitor.indicators.ma import ema, sma
from monitor.instruments import InstrumentType
from monitor.rules.base import Rule, Signal, parse_applies_to


class MaCrossReversalRule(Rule):
    """MA short / long cross — golden cross (up) or death cross (down).

    Fires on the FIRST bar where MA(short) crosses MA(long):
      direction=up   黃金交叉: prev MA_s ≤ MA_l, cur MA_s > MA_l
      direction=down 死亡交叉: prev MA_s ≥ MA_l, cur MA_s < MA_l
    """

    def __init__(
        self,
        name: str,
        timeframe: str,
        short: int = 5,
        long: int = 20,
        direction: str = "up",
        ma_type: str = "ema",
        cooldown_minutes: int = 30,
        applies_to: set[InstrumentType] | None = None,
    ) -> None:
        if direction not in ("up", "down"):
            raise ValueError(f"direction must be 'up' or 'down', got {direction!r}")
        if ma_type not in ("ema", "sma"):
            raise ValueError(f"ma_type must be 'ema' or 'sma', got {ma_type!r}")
        if short >= long:
            raise ValueError(f"short ({short}) must be < long ({long})")
        self._name = name
        self._timeframe = timeframe
        self._short = short
        self._long = long
        self._direction = direction
        self._ma_type = ma_type
        self._cooldown = cooldown_minutes
        self._applies_to = applies_to or set(InstrumentType)

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

    @property
    def expected_direction(self) -> str:
        return "long" if self._direction == "up" else "short"

    @property
    def applies_to(self) -> set[InstrumentType]:
        return self._applies_to

    @classmethod
    def from_config(cls, cfg: dict) -> "MaCrossReversalRule":
        return cls(
            name=cfg["name"],
            timeframe=cfg.get("timeframe", "5m"),
            short=cfg.get("short", 5),
            long=cfg.get("long", 20),
            direction=cfg.get("direction", "up"),
            ma_type=cfg.get("ma_type", "ema"),
            cooldown_minutes=cfg.get("cooldown_minutes", 30),
            applies_to=parse_applies_to(cfg),
        )

    # -- Evaluation -----------------------------------------------------------

    def evaluate(self, symbol: str, bars: pd.DataFrame) -> Signal | None:
        if len(bars) < self._long + 2:
            return None

        ma_fn = ema if self._ma_type == "ema" else sma
        ma_s = ma_fn(bars["close"], self._short)
        ma_l = ma_fn(bars["close"], self._long)

        prev_s, cur_s = ma_s.iloc[-2], ma_s.iloc[-1]
        prev_l, cur_l = ma_l.iloc[-2], ma_l.iloc[-1]
        if any(pd.isna(v) for v in (prev_s, prev_l, cur_s, cur_l)):
            return None

        if self._direction == "up":
            crossed = prev_s <= prev_l and cur_s > cur_l
        else:
            crossed = prev_s >= prev_l and cur_s < cur_l
        if not crossed:
            return None

        return self._build_signal(symbol, bars, cur_s, cur_l)

    def _build_signal(
        self,
        symbol: str,
        bars: pd.DataFrame,
        cur_s: float,
        cur_l: float,
    ) -> Signal:
        cur_bar = bars.iloc[-1]
        bar_time = bars.index[-1]
        ts_str = bar_time.strftime("%H:%M") if hasattr(bar_time, "strftime") else str(bar_time)

        cross_label = "黃金交叉" if self._direction == "up" else "死亡交叉"
        emoji = "🟢" if self._direction == "up" else "🔴"
        arrow = "↗" if self._direction == "up" else "↘"
        ma_tag = self._ma_type.upper()

        vol_avg = bars["volume"].iloc[-21:-1].mean()
        vol_ratio = float(cur_bar["volume"] / vol_avg) if vol_avg and vol_avg > 0 else 0.0

        message = (
            f"{emoji} {self._name} 觸發\n"
            f"{symbol} {self._timeframe} @ {ts_str}\n"
            f"收盤 {cur_bar['close']:.2f}\n"
            f"{ma_tag}{self._short}({cur_s:.2f}) {arrow} "
            f"{ma_tag}{self._long}({cur_l:.2f}) {cross_label}\n"
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
                f"{self._ma_type}_{self._short}": float(cur_s),
                f"{self._ma_type}_{self._long}": float(cur_l),
                "volume": int(cur_bar["volume"]),
                "vol_ratio": round(vol_ratio, 2),
            },
        )
