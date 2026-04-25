from datetime import timezone

import pandas as pd
import pytest

from monitor.data.historical import TIMEFRAMES, resample_bars


def _make_1m(n: int = 30) -> pd.DataFrame:
    """Generate n 1-min bars starting at 09:01 Asia/Taipei."""
    idx = pd.date_range(
        "2024-01-02 09:01",
        periods=n,
        freq="1min",
        tz="Asia/Taipei",
        name="ts",
    )
    return pd.DataFrame(
        {
            "open": [float(i + 100) for i in range(n)],
            "high": [float(i + 101) for i in range(n)],
            "low": [float(i + 99) for i in range(n)],
            "close": [float(i + 100) for i in range(n)],
            "volume": [100] * n,
        },
        index=idx,
    )


def test_resample_5m_bar_count():
    df = _make_1m(30)
    out = resample_bars(df, "5min")
    # 30 1-min bars → 6 complete 5-min bars
    assert len(out) == 6


def test_resample_5m_ohlcv():
    df = _make_1m(5)
    out = resample_bars(df, "5min")
    assert len(out) == 1
    row = out.iloc[0]
    assert row["open"] == df["open"].iloc[0]   # first
    assert row["high"] == df["high"].max()
    assert row["low"] == df["low"].min()
    assert row["close"] == df["close"].iloc[-1]  # last
    assert row["volume"] == df["volume"].sum()


def test_resample_15m_bar_count():
    df = _make_1m(30)
    out = resample_bars(df, "15min")
    assert len(out) == 2


def test_resample_label_is_right():
    df = _make_1m(5)  # 09:01–09:05
    out = resample_bars(df, "5min")
    # With label='right' the bar should be labeled 09:05
    assert out.index[0].hour == 9
    assert out.index[0].minute == 5


def test_resample_all_timeframes():
    df = _make_1m(60)
    for tf, rule in TIMEFRAMES.items():
        if rule is None:
            continue
        out = resample_bars(df, rule)
        assert not out.empty, f"Empty result for {tf}"
        assert list(out.columns) == ["open", "high", "low", "close", "volume"]
