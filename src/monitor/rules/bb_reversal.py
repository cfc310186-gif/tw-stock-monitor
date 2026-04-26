from __future__ import annotations

import pandas as pd

from monitor.indicators.bbands import bbands
from monitor.rules.base import Rule, Signal


class BbReversalRule(Rule):
    """Bollinger Band outer-bar reversal + body-engulfing + volume surge.

    All five conditions must hold on the last two bars:
      1. prev bar closed OUTSIDE the BB band (lower or upper side)
      2. current bar colour is opposite to prev bar (豬羊變色)
      3. current bar close is INSIDE the BB band
      4. current bar's body engulfs prev's body — i.e. the reversal is
         decisive enough that cur close passes through prev open
           lower side (bullish): cur close > prev open
           upper side (bearish): cur close < prev open
      5. current bar's volume ≥ min_volume_ratio × prior 20-bar avg volume
    """

    def __init__(
        self,
        name: str,
        timeframe: str,
        side: str = "lower",
        period: int = 20,
        stddev: float = 2.0,
        cooldown_minutes: int = 30,
        min_volume_ratio: float = 1.5,
    ) -> None:
        if side not in ("lower", "upper"):
            raise ValueError(f"side must be 'lower' or 'upper', got {side!r}")
        self._name = name
        self._timeframe = timeframe
        self._side = side
        self._period = period
        self._stddev = stddev
        self._cooldown = cooldown_minutes
        self._min_volume_ratio = min_volume_ratio

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
        return "long" if self._side == "lower" else "short"

    @classmethod
    def from_config(cls, cfg: dict) -> "BbReversalRule":
        return cls(
            name=cfg["name"],
            timeframe=cfg.get("timeframe", "5m"),
            side=cfg.get("side", "lower"),
            period=cfg.get("period", 20),
            stddev=cfg.get("stddev", 2.0),
            cooldown_minutes=cfg.get("cooldown_minutes", 30),
            min_volume_ratio=cfg.get("min_volume_ratio", 1.5),
        )

    # -- Evaluation -----------------------------------------------------------

    def evaluate(self, symbol: str, bars: pd.DataFrame) -> Signal | None:
        if len(bars) < self._period + 2:
            return None

        bb = bbands(bars["close"], self._period, self._stddev)

        prev_bar = bars.iloc[-2]
        cur_bar = bars.iloc[-1]
        bb_prev = bb.iloc[-2]
        bb_cur = bb.iloc[-1]

        # 1. prev bar closed outside the target band
        if self._side == "lower":
            if prev_bar["close"] >= bb_prev["lower"]:
                return None
        else:
            if prev_bar["close"] <= bb_prev["upper"]:
                return None

        # 2. candle colour flip (豬羊變色)
        prev_green = prev_bar["close"] > prev_bar["open"]
        cur_green = cur_bar["close"] > cur_bar["open"]
        if prev_green == cur_green:
            return None

        # 3. current close inside BB
        if not (bb_cur["lower"] <= cur_bar["close"] <= bb_cur["upper"]):
            return None

        # 4. body-engulfing: cur close passes through prev open
        if self._side == "lower":
            if cur_bar["close"] <= prev_bar["open"]:
                return None
        else:
            if cur_bar["close"] >= prev_bar["open"]:
                return None

        # 5. volume surge vs prior 20-bar average
        vol_avg = bars["volume"].iloc[-21:-1].mean()
        if not vol_avg or vol_avg <= 0:
            return None
        vol_ratio = float(cur_bar["volume"]) / float(vol_avg)
        if vol_ratio < self._min_volume_ratio:
            return None

        return self._build_signal(symbol, bars, prev_bar, cur_bar, bb_cur,
                                  cur_green, vol_ratio)

    def _build_signal(
        self,
        symbol: str,
        bars: pd.DataFrame,
        prev_bar: pd.Series,
        cur_bar: pd.Series,
        bb_cur: pd.Series,
        cur_green: bool,
        vol_ratio: float,
    ) -> Signal:
        bar_time = bars.index[-1]
        ts_str = bar_time.strftime("%H:%M") if hasattr(bar_time, "strftime") else str(bar_time)
        band_label = "下軌外" if self._side == "lower" else "上軌外"
        colour_label = "紅K" if cur_green else "黑K"

        message = (
            f"📈 {self._name} 觸發\n"
            f"{symbol} {self._timeframe} @ {ts_str}\n"
            f"收盤 {cur_bar['close']:.2f}\n"
            f"布林{band_label}反轉吞噬｜{colour_label}吃掉前根實體\n"
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
                "prev_open": float(prev_bar["open"]),
                "bb_upper": float(bb_cur["upper"]),
                "bb_lower": float(bb_cur["lower"]),
                "volume": int(cur_bar["volume"]),
                "vol_ratio": round(vol_ratio, 2),
            },
        )
