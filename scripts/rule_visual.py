"""Visual sanity-check of every implemented rule.

For each rule we construct a synthetic bar series that we *know* should
trigger, run rule.evaluate(), and print:
  - the rule conditions
  - an ASCII candlestick chart of the relevant tail
  - the actual signal message (proves the rule fired)

Run: python3 scripts/rule_visual.py
"""
from __future__ import annotations

import pandas as pd

from monitor.indicators.bbands import bbands
from monitor.indicators.ma import sma
from monitor.rules.bb_reversal import BbReversalRule
from monitor.rules.ma_cross_reversal import MaCrossReversalRule
from monitor.rules.range_breakout import RangeBreakoutRule


# ---------------------------------------------------------------------------
# Bar construction helper
# ---------------------------------------------------------------------------

def make_bars(rows: list[dict]) -> pd.DataFrame:
    n = len(rows)
    idx = pd.date_range(
        "2024-01-02 09:01", periods=n, freq="1min", tz="Asia/Taipei", name="ts"
    )
    return pd.DataFrame(rows, index=idx)


def closes_to_bars(
    closes: list[float], opens: list[float] | None = None,
    highs: list[float] | None = None, lows: list[float] | None = None,
) -> pd.DataFrame:
    n = len(closes)
    opens = opens if opens is not None else closes[:]
    highs = highs if highs is not None else [max(o, c) + 0.3 for o, c in zip(opens, closes)]
    lows = lows if lows is not None else [min(o, c) - 0.3 for o, c in zip(opens, closes)]
    rows = [
        {"open": o, "high": h, "low": l, "close": c, "volume": 1000}
        for o, h, l, c in zip(opens, highs, lows, closes)
    ]
    return make_bars(rows)


# ---------------------------------------------------------------------------
# ASCII candle renderer
# ---------------------------------------------------------------------------

def render(
    df: pd.DataFrame,
    last_n: int = 12,
    height: int = 14,
    overlay: dict[str, list[float]] | None = None,
    annotations: dict[int, str] | None = None,
) -> str:
    """Render ASCII candles for the last `last_n` bars.

    overlay: dict of {label: per-bar value list (same length as df)} drawn as
             lowercase letters at the bar's row.
    annotations: dict of {position-from-end (0=last bar): "label"}.
    """
    df = df.iloc[-last_n:].reset_index(drop=True)
    overlay = overlay or {}
    annotations = annotations or {}

    high_max = df[["high", "low", "open", "close"]].values.max()
    low_min = df[["high", "low", "open", "close"]].values.min()
    for vals in overlay.values():
        tail = pd.Series(vals).iloc[-last_n:]
        if not tail.dropna().empty:
            high_max = max(high_max, tail.dropna().max())
            low_min = min(low_min, tail.dropna().min())
    pad = (high_max - low_min) * 0.05 or 1.0
    high_max += pad
    low_min -= pad
    rng = high_max - low_min

    def to_row(price: float) -> int:
        return min(height - 1, max(0, int((high_max - price) / rng * (height - 1))))

    cols_per_bar = 3
    width = last_n * cols_per_bar + 2
    grid = [[" "] * width for _ in range(height)]

    for i in range(len(df)):
        col = i * cols_per_bar + 1
        bar = df.iloc[i]
        h_r = to_row(bar["high"])
        l_r = to_row(bar["low"])
        o_r = to_row(bar["open"])
        c_r = to_row(bar["close"])
        body_top = min(o_r, c_r)
        body_bot = max(o_r, c_r)
        is_green = bar["close"] > bar["open"]
        body = "│" if is_green else "█"
        for r in range(h_r, l_r + 1):
            if body_top <= r <= body_bot:
                grid[r][col] = body
            else:
                grid[r][col] = "│"

    overlay_chars = {"upper": "u", "lower": "l", "middle": "m",
                     "ma_short": "s", "ma_long": "L"}
    for label, vals in overlay.items():
        ch = overlay_chars.get(label, label[0])
        tail = list(vals)[-last_n:]
        for i, v in enumerate(tail):
            if pd.isna(v):
                continue
            r = to_row(float(v))
            col = i * cols_per_bar + 1
            if grid[r][col] == " ":
                grid[r][col] = ch

    out = []
    for r in range(height):
        price = high_max - r / (height - 1) * rng
        out.append(f"  {price:7.2f} │ " + "".join(grid[r]))
    out.append(f"  {'':>7s} └─" + "─" * width)

    if annotations:
        label_row = " " * 12
        for i in range(last_n):
            from_end = last_n - 1 - i
            tag = annotations.get(from_end, "")
            label_row += tag.ljust(cols_per_bar)[:cols_per_bar]
        out.append(label_row)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Demos
# ---------------------------------------------------------------------------

def demo_bb_reversal_lower():
    print("=" * 78)
    print("  bb_reversal  (side=lower)  — 跌破下軌後，下一根反向 K 收回軌道內")
    print("=" * 78)
    print("  條件:")
    print("    1. 前一根 close < BB_lower")
    print("    2. 前一根 vs 當根：紅黑 K 顏色相反 (豬羊變色)")
    print("    3. 當根 close 回到 BB 軌道內")
    print()

    closes = [100.0] * 22 + [88.0, 96.0]
    opens = [100.0] * 22 + [100.0, 88.0]
    df = closes_to_bars(closes, opens=opens)
    bb = bbands(df["close"], period=20, stddev=2.0)

    rule = BbReversalRule(name="bb_reversal_5m", timeframe="5m", side="lower")
    sig = rule.evaluate("2330", df)

    print(render(df, last_n=12,
                 overlay={"upper": bb["upper"].tolist(),
                          "middle": bb["middle"].tolist(),
                          "lower": bb["lower"].tolist()},
                 annotations={1: "prev", 0: "cur"}))
    print()
    print("  圖例: │ 紅K (close>open)   █ 黑K (close<open)   "
          "u/m/l = BB 上/中/下軌")
    print()
    if sig:
        print("  ✅ 觸發訊息:")
        for line in sig.message.split("\n"):
            print("    " + line)
    else:
        print("  ❌ 未觸發 (測試資料設計錯誤)")
    print()


def demo_bb_reversal_upper():
    print("=" * 78)
    print("  bb_reversal  (side=upper)  — 突破上軌後，下一根反向 K 收回軌道內")
    print("=" * 78)
    print("  條件:")
    print("    1. 前一根 close > BB_upper")
    print("    2. 前一根 vs 當根：紅黑 K 顏色相反")
    print("    3. 當根 close 回到 BB 軌道內")
    print()

    closes = [100.0] * 22 + [115.0, 101.0]
    opens = [100.0] * 22 + [100.0, 116.0]
    df = closes_to_bars(closes, opens=opens)
    bb = bbands(df["close"], period=20, stddev=2.0)

    rule = BbReversalRule(name="bb_reversal_upper_5m", timeframe="5m", side="upper")
    sig = rule.evaluate("2330", df)

    print(render(df, last_n=12,
                 overlay={"upper": bb["upper"].tolist(),
                          "middle": bb["middle"].tolist(),
                          "lower": bb["lower"].tolist()},
                 annotations={1: "prev", 0: "cur"}))
    print()
    if sig:
        print("  ✅ 觸發訊息:")
        for line in sig.message.split("\n"):
            print("    " + line)
    print()


def demo_ma_cross_up():
    print("=" * 78)
    print("  ma_cross_reversal  (direction=up)  — MA(5) 由下往上穿越 MA(20)")
    print("=" * 78)
    print("  條件:")
    print("    1. 前一根: MA_short ≤ MA_long")
    print("    2. 當根:   MA_short >  MA_long  (黃金交叉)")
    print()

    # 20 根平 100，1 根尖刺 80 把短MA壓低，5 根回 100；最後一根時 80 離開短MA
    # 視窗，短MA 重回 100，與長MA(99) 形成黃金交叉。
    closes = [100.0] * 20 + [80.0, 100.0, 100.0, 100.0, 100.0, 100.0]
    opens = closes[:]
    opens[20] = 100.0  # 80 是黑K
    df = closes_to_bars(closes, opens=opens)
    ma_s = sma(df["close"], 5)
    ma_l = sma(df["close"], 20)

    rule = MaCrossReversalRule(name="ma_cross_reversal_up_5m", timeframe="5m",
                                short=5, long=20, direction="up", ma_type="sma")
    sig = rule.evaluate("2330", df)

    print(render(df, last_n=12,
                 overlay={"ma_short": ma_s.tolist(),
                          "ma_long": ma_l.tolist()},
                 annotations={1: "prev", 0: "cur"}))
    print()
    print("  圖例: s = SMA(5)   L = SMA(20)")
    print()
    if sig:
        print("  ✅ 觸發訊息:")
        for line in sig.message.split("\n"):
            print("    " + line)
    print()


def demo_ma_cross_down():
    print("=" * 78)
    print("  ma_cross_reversal  (direction=down)  — MA(5) 由上往下穿越 MA(20)")
    print("=" * 78)
    print("  條件:")
    print("    1. 前一根: MA_short ≥ MA_long")
    print("    2. 當根:   MA_short <  MA_long  (死亡交叉)")
    print()

    closes = [100.0] * 20 + [120.0, 100.0, 100.0, 100.0, 100.0, 100.0]
    opens = closes[:]
    opens[20] = 100.0  # 120 是紅K
    df = closes_to_bars(closes, opens=opens)
    ma_s = sma(df["close"], 5)
    ma_l = sma(df["close"], 20)

    rule = MaCrossReversalRule(name="ma_cross_reversal_down_5m", timeframe="5m",
                                short=5, long=20, direction="down", ma_type="sma")
    sig = rule.evaluate("2330", df)

    print(render(df, last_n=12,
                 overlay={"ma_short": ma_s.tolist(),
                          "ma_long": ma_l.tolist()},
                 annotations={1: "prev", 0: "cur"}))
    print()
    if sig:
        print("  ✅ 觸發訊息:")
        for line in sig.message.split("\n"):
            print("    " + line)
    print()


def demo_range_breakout_up():
    print("=" * 78)
    print("  range_breakout  (direction=up)  — 收盤突破前 N 根最高點")
    print("=" * 78)
    print("  條件:")
    print("    1. 當根 close > 前 N 根 high 的最大值")
    print("    2. 前一根並未已突破 (僅在『第一根』突破時發訊號)")
    print()

    # 22 根 high <= 100；前一根 close=99；當根 close=102 (突破)
    closes = [99.5] * 21 + [99.0, 102.0]
    highs = [100.0] * 21 + [99.5, 102.5]
    lows = [98.0] * 23
    opens = [99.5] * 21 + [99.0, 99.5]
    df = closes_to_bars(closes, opens=opens, highs=highs, lows=lows)

    rule = RangeBreakoutRule(name="range_breakout_up_15m", timeframe="15m",
                             period=20, direction="up")
    sig = rule.evaluate("2330", df)

    # Pre-compute the breakout level for each bar (rolling 20-high of prior bars)
    levels = df["high"].shift(1).rolling(20, min_periods=20).max()
    print(render(df, last_n=12,
                 overlay={"upper": levels.tolist()},
                 annotations={1: "prev", 0: "cur"}))
    print()
    print("  圖例: u = 前 20 根 high 的最高點 (突破門檻)")
    print()
    if sig:
        print("  ✅ 觸發訊息:")
        for line in sig.message.split("\n"):
            print("    " + line)
    print()


def demo_range_breakout_down():
    print("=" * 78)
    print("  range_breakout  (direction=down)  — 收盤跌破前 N 根最低點")
    print("=" * 78)
    print("  條件:")
    print("    1. 當根 close < 前 N 根 low 的最小值")
    print("    2. 前一根並未已跌破")
    print()

    closes = [97.0] * 21 + [96.0, 92.0]
    highs = [100.0] * 23
    lows = [95.0] * 21 + [95.5, 92.0]
    opens = [97.0] * 21 + [97.0, 96.0]
    df = closes_to_bars(closes, opens=opens, highs=highs, lows=lows)

    rule = RangeBreakoutRule(name="range_breakout_down_15m", timeframe="15m",
                             period=20, direction="down")
    sig = rule.evaluate("2330", df)

    levels = df["low"].shift(1).rolling(20, min_periods=20).min()
    print(render(df, last_n=12,
                 overlay={"lower": levels.tolist()},
                 annotations={1: "prev", 0: "cur"}))
    print()
    print("  圖例: l = 前 20 根 low 的最低點 (跌破門檻)")
    print()
    if sig:
        print("  ✅ 觸發訊息:")
        for line in sig.message.split("\n"):
            print("    " + line)
    print()


# ---------------------------------------------------------------------------

def main() -> None:
    demo_bb_reversal_lower()
    demo_bb_reversal_upper()
    demo_ma_cross_up()
    demo_ma_cross_down()
    demo_range_breakout_up()
    demo_range_breakout_down()


if __name__ == "__main__":
    main()
