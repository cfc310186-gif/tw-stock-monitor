"""Generate PNG candlestick charts for each rule's trigger scenario.

Saves one PNG per rule variant to docs/rules/, suitable for embedding in
docs or viewing in a PR. Each chart marks `prev` and `cur` bars with
arrows and overlays the relevant indicator.

Run: python3 scripts/rule_charts.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless backend
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import pandas as pd

# Pick a CJK-capable font if one is installed (Linux: wqy-zenhei; macOS: PingFang;
# Windows: Microsoft JhengHei). Fallback: matplotlib's default — Chinese will
# render as boxes but won't crash.
_CJK_FONT = None
for _name in ("WenQuanYi Zen Hei", "Noto Sans CJK TC", "PingFang TC",
              "Microsoft JhengHei", "Heiti TC", "SimHei"):
    if any(_name.lower() in f.name.lower() for f in fm.fontManager.ttflist):
        _CJK_FONT = _name
        plt.rcParams["font.family"] = _name
        plt.rcParams["font.monospace"] = [_name, "DejaVu Sans Mono"]
        break
plt.rcParams["axes.unicode_minus"] = False

from monitor.indicators.bbands import bbands
from monitor.indicators.ma import sma
from monitor.rules.bb_reversal import BbReversalRule
from monitor.rules.ma_cross_reversal import MaCrossReversalRule
from monitor.rules.range_breakout import RangeBreakoutRule

OUT_DIR = Path(__file__).parent.parent / "docs" / "rules"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Bar helpers
# ---------------------------------------------------------------------------

def make_bars(closes, opens=None, highs=None, lows=None, volumes=None) -> pd.DataFrame:
    n = len(closes)
    opens = opens if opens is not None else closes[:]
    highs = highs if highs is not None else [max(o, c) + 0.3 for o, c in zip(opens, closes)]
    lows = lows if lows is not None else [min(o, c) - 0.3 for o, c in zip(opens, closes)]
    volumes = volumes if volumes is not None else [1000] * n
    idx = pd.date_range(
        "2024-01-02 09:01", periods=n, freq="1min", tz="Asia/Taipei", name="ts"
    )
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes,
         "volume": volumes},
        index=idx,
    )


# ---------------------------------------------------------------------------
# Candlestick renderer
# ---------------------------------------------------------------------------

def plot_candles(
    df: pd.DataFrame,
    title: str,
    overlays: dict[str, tuple[pd.Series, str]] | None = None,
    annotations: dict[int, str] | None = None,
    out_path: Path | None = None,
    last_n: int = 14,
    message: str | None = None,
    show_volume: bool = False,
):
    """Plot candlesticks with optional indicator overlays + signal text.

    overlays: {label: (series, color)}
    annotations: {position-from-end: "label"} (e.g., {0: "cur", 1: "prev"})
    show_volume: add a stacked volume sub-pane underneath. The current bar
                 is highlighted to make the volume-surge condition visible.
    """
    overlays = overlays or {}
    annotations = annotations or {}
    df = df.iloc[-last_n:].reset_index(drop=True)
    n = len(df)

    if show_volume:
        fig, (ax, ax_vol) = plt.subplots(
            2, 1, figsize=(10, 7), sharex=True,
            gridspec_kw={"height_ratios": [3, 1]},
        )
    else:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax_vol = None

    width = 0.6
    for i, row in df.iterrows():
        is_bullish = row["close"] > row["open"]   # 紅K
        # TW convention: 紅K (close > open) = red body; 黑K (close < open) = green body
        color = "#d62728" if is_bullish else "#2ca02c"
        ax.vlines(i, row["low"], row["high"], color="black", linewidth=0.8, zorder=2)
        body_low = min(row["open"], row["close"])
        body_height = abs(row["close"] - row["open"]) or 0.05
        ax.add_patch(plt.Rectangle(
            (i - width / 2, body_low), width, body_height,
            facecolor=color, edgecolor="black", linewidth=0.6, zorder=3,
        ))

    for label, (series, color) in overlays.items():
        tail = list(series)[-last_n:]
        ax.plot(range(n), tail, color=color, linewidth=1.5,
                label=label, zorder=4)

    y_top = df["high"].max()
    y_bot = df["low"].min()
    pad = (y_top - y_bot) * 0.08
    for from_end, tag in annotations.items():
        i = n - 1 - from_end
        ax.annotate(tag, xy=(i, df["high"].iloc[i]),
                    xytext=(i, df["high"].iloc[i] + pad),
                    ha="center", fontsize=11, fontweight="bold",
                    color="#0066cc",
                    arrowprops=dict(arrowstyle="->", color="#0066cc",
                                    lw=1.2, shrinkA=0, shrinkB=2))

    ax.set_xlim(-0.5, n - 0.5)
    ax.set_ylim(y_bot - pad * 2, y_top + pad * 3)
    ax.set_ylabel("price")
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.grid(True, axis="y", linestyle=":", alpha=0.4)
    if overlays:
        ax.legend(loc="upper left", fontsize=9)

    if ax_vol is not None:
        colors = ["#888888"] * n
        colors[-1] = "#0066cc"   # highlight cur volume bar
        ax_vol.bar(range(n), df["volume"], color=colors, edgecolor="black",
                   linewidth=0.4, width=0.7)
        # Reference line: prior 20-bar avg (matches the rule's gate metric)
        prior_avg = df["volume"].iloc[:-1].tail(20).mean() if n > 1 else 0
        ax_vol.axhline(prior_avg, color="#cc6600", linestyle="--", linewidth=1,
                       label=f"prior avg ≈ {int(prior_avg):,}")
        ax_vol.legend(loc="upper left", fontsize=8)
        ax_vol.set_ylabel("volume", fontsize=9)
        ax_vol.grid(True, axis="y", linestyle=":", alpha=0.3)
        ax_vol.set_xticks(range(n))
        ax_vol.set_xticklabels([f"-{n - 1 - i}" if i < n - 1 else "0" for i in range(n)],
                                fontsize=8)
        ax_vol.set_xlabel("bars from current (0 = trigger bar)")
    else:
        ax.set_xticks(range(n))
        ax.set_xticklabels([f"-{n - 1 - i}" if i < n - 1 else "0" for i in range(n)],
                           fontsize=8)
        ax.set_xlabel("bars from current (0 = trigger bar)")

    if message:
        # Strip emoji codepoints — most DejaVu/WQY fonts don't ship colour-emoji
        # glyphs, and matplotlib will substitute boxes if we leave them in.
        cleaned = "".join(c for c in message if ord(c) < 0x2600 or 0x3000 <= ord(c) < 0xFB00)
        fig.text(0.02, 0.02, cleaned.strip(), fontsize=8,
                 family=_CJK_FONT or "monospace",
                 verticalalignment="bottom",
                 bbox=dict(facecolor="#f8f8f8", edgecolor="#cccccc",
                           boxstyle="round,pad=0.4"))

    plt.tight_layout()
    if message:
        plt.subplots_adjust(bottom=0.22)
    if out_path:
        fig.savefig(out_path, dpi=130)
        print(f"  wrote {out_path}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Per-rule scenarios
# ---------------------------------------------------------------------------

def chart_bb_reversal_lower():
    # prev 黑K 100 → 86 (跌出下軌); cur 紅K 85 → 101 (回到軌道內 + 吞噬 prev_open)
    closes = [100.0] * 22 + [86.0, 101.0]
    opens = [100.0] * 22 + [100.0, 85.0]
    volumes = [1000] * 22 + [1500, 3000]      # cur ≈ 2.85× prior avg
    df = make_bars(closes, opens=opens, volumes=volumes)
    bb = bbands(df["close"], period=20, stddev=2.0)
    rule = BbReversalRule(name="bb_reversal_5m", timeframe="5m", side="lower")
    sig = rule.evaluate("2330", df)
    plot_candles(
        df,
        title="bb_reversal (side=lower) — 跌出下軌→吞噬反轉紅K + 量增",
        overlays={
            "BB upper": (bb["upper"], "#888888"),
            "BB middle": (bb["middle"], "#444444"),
            "BB lower": (bb["lower"], "#888888"),
        },
        annotations={1: "prev", 0: "cur"},
        message=sig.message if sig else "(未觸發)",
        out_path=OUT_DIR / "bb_reversal_lower.png",
        show_volume=True,
    )


def chart_bb_reversal_upper():
    # prev 紅K 100 → 115 (突破上軌); cur 黑K 116 → 99 (回到軌道內 + 吞噬 prev_open)
    closes = [100.0] * 22 + [115.0, 99.0]
    opens = [100.0] * 22 + [100.0, 116.0]
    volumes = [1000] * 22 + [1500, 3000]
    df = make_bars(closes, opens=opens, volumes=volumes)
    bb = bbands(df["close"], period=20, stddev=2.0)
    rule = BbReversalRule(name="bb_reversal_upper_5m", timeframe="5m", side="upper")
    sig = rule.evaluate("2330", df)
    plot_candles(
        df,
        title="bb_reversal (side=upper) — 突破上軌→吞噬反轉黑K + 量增",
        overlays={
            "BB upper": (bb["upper"], "#888888"),
            "BB middle": (bb["middle"], "#444444"),
            "BB lower": (bb["lower"], "#888888"),
        },
        annotations={1: "prev", 0: "cur"},
        message=sig.message if sig else "(未觸發)",
        out_path=OUT_DIR / "bb_reversal_upper.png",
        show_volume=True,
    )


def chart_ma_cross_up():
    closes = [100.0] * 20 + [80.0, 100.0, 100.0, 100.0, 100.0, 100.0]
    opens = closes[:]
    opens[20] = 100.0  # 80 是黑K
    df = make_bars(closes, opens=opens)
    ma_s = sma(df["close"], 5)
    ma_l = sma(df["close"], 20)
    rule = MaCrossReversalRule(
        name="ma_cross_reversal_up_5m", timeframe="5m",
        short=5, long=20, direction="up", ma_type="sma",
    )
    sig = rule.evaluate("2330", df)
    plot_candles(
        df,
        title="ma_cross_reversal (direction=up) — SMA5 由下往上穿越 SMA20",
        overlays={"SMA5": (ma_s, "#0066cc"), "SMA20": (ma_l, "#cc6600")},
        annotations={1: "prev", 0: "cur"},
        message=sig.message if sig else "(未觸發)",
        out_path=OUT_DIR / "ma_cross_reversal_up.png",
    )


def chart_ma_cross_down():
    closes = [100.0] * 20 + [120.0, 100.0, 100.0, 100.0, 100.0, 100.0]
    opens = closes[:]
    opens[20] = 100.0  # 120 是紅K
    df = make_bars(closes, opens=opens)
    ma_s = sma(df["close"], 5)
    ma_l = sma(df["close"], 20)
    rule = MaCrossReversalRule(
        name="ma_cross_reversal_down_5m", timeframe="5m",
        short=5, long=20, direction="down", ma_type="sma",
    )
    sig = rule.evaluate("2330", df)
    plot_candles(
        df,
        title="ma_cross_reversal (direction=down) — SMA5 由上往下穿越 SMA20",
        overlays={"SMA5": (ma_s, "#0066cc"), "SMA20": (ma_l, "#cc6600")},
        annotations={1: "prev", 0: "cur"},
        message=sig.message if sig else "(未觸發)",
        out_path=OUT_DIR / "ma_cross_reversal_down.png",
    )


def chart_range_breakout_up():
    closes = [99.5] * 21 + [99.0, 102.0]
    highs = [100.0] * 21 + [99.5, 102.5]
    lows = [98.0] * 23
    opens = [99.5] * 21 + [99.0, 99.5]
    volumes = [1000] * 22 + [3000]            # cur 3× prior avg
    df = make_bars(closes, opens=opens, highs=highs, lows=lows, volumes=volumes)
    levels = df["high"].shift(1).rolling(20, min_periods=20).max()
    rule = RangeBreakoutRule(
        name="range_breakout_up_15m", timeframe="15m",
        period=20, direction="up",
    )
    sig = rule.evaluate("2330", df)
    plot_candles(
        df,
        title="range_breakout (direction=up) — 突破前 20 根高點 + 量增確認",
        overlays={"prior 20 高": (levels, "#cc3344")},
        annotations={1: "prev", 0: "cur"},
        message=sig.message if sig else "(未觸發)",
        out_path=OUT_DIR / "range_breakout_up.png",
        show_volume=True,
    )


def chart_range_breakout_down():
    closes = [97.0] * 21 + [96.0, 92.0]
    highs = [100.0] * 23
    lows = [95.0] * 21 + [95.5, 92.0]
    opens = [97.0] * 21 + [97.0, 96.0]
    volumes = [1000] * 22 + [3000]
    df = make_bars(closes, opens=opens, highs=highs, lows=lows, volumes=volumes)
    levels = df["low"].shift(1).rolling(20, min_periods=20).min()
    rule = RangeBreakoutRule(
        name="range_breakout_down_15m", timeframe="15m",
        period=20, direction="down",
    )
    sig = rule.evaluate("2330", df)
    plot_candles(
        df,
        title="range_breakout (direction=down) — 跌破前 20 根低點 + 量增確認",
        overlays={"prior 20 低": (levels, "#22aa55")},
        annotations={1: "prev", 0: "cur"},
        message=sig.message if sig else "(未觸發)",
        out_path=OUT_DIR / "range_breakout_down.png",
        show_volume=True,
    )


def main() -> None:
    chart_bb_reversal_lower()
    chart_bb_reversal_upper()
    chart_ma_cross_up()
    chart_ma_cross_down()
    chart_range_breakout_up()
    chart_range_breakout_down()
    print(f"\n所有圖檔已輸出到 {OUT_DIR}/")


if __name__ == "__main__":
    main()
