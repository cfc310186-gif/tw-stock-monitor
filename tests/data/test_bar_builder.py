from datetime import datetime

import pandas as pd
import pytest

from monitor.data.bar_builder import BarBuilder
from monitor.data.historical import TIMEFRAMES


def _make_hist(n: int = 60) -> dict[str, dict[str, pd.DataFrame]]:
    """Build a minimal hist dict with one symbol and all timeframes."""
    idx = pd.date_range(
        "2024-01-02 09:01",
        periods=n,
        freq="1min",
        tz="Asia/Taipei",
        name="ts",
    )
    df_1m = pd.DataFrame(
        {
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.0] * n,
            "volume": [100] * n,
        },
        index=idx,
    )
    from monitor.data.historical import resample_bars, TIMEFRAMES

    frames: dict[str, pd.DataFrame] = {"1m": df_1m}
    for tf, rule in TIMEFRAMES.items():
        if rule is not None:
            frames[tf] = resample_bars(df_1m, rule)

    return {"2330": frames}


def test_get_bars_returns_dataframe():
    builder = BarBuilder(_make_hist())
    df = builder.get_bars("2330", "1m")
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_get_bars_unknown_symbol():
    builder = BarBuilder(_make_hist())
    df = builder.get_bars("9999", "1m")
    assert df.empty


def test_get_bars_window_respected():
    hist = _make_hist(n=60)
    builder = BarBuilder(hist, window=10)
    df = builder.get_bars("2330", "1m")
    assert len(df) <= 10


def test_on_snapshot_first_call_no_closed():
    builder = BarBuilder(_make_hist())
    ts = datetime(2024, 1, 2, 9, 30, 0, tzinfo=pd.Timestamp("now", tz="Asia/Taipei").tzinfo)
    closed = builder.on_snapshot("2330", 105.0, 1000, ts)
    assert closed == []


def test_on_snapshot_closes_1m_bar():
    builder = BarBuilder(_make_hist())
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Asia/Taipei")

    t1 = datetime(2024, 1, 2, 9, 30, 0, tzinfo=tz)
    t2 = datetime(2024, 1, 2, 9, 31, 0, tzinfo=tz)

    builder.on_snapshot("2330", 100.0, 1000, t1)
    closed = builder.on_snapshot("2330", 101.0, 1100, t2)
    assert "1m" in closed


def test_on_snapshot_same_minute_no_close():
    builder = BarBuilder(_make_hist())
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Asia/Taipei")
    t1 = datetime(2024, 1, 2, 9, 30, 0, tzinfo=tz)
    t2 = datetime(2024, 1, 2, 9, 30, 30, tzinfo=tz)

    builder.on_snapshot("2330", 100.0, 1000, t1)
    closed = builder.on_snapshot("2330", 102.0, 1050, t2)
    assert closed == []


def test_symbols_returns_loaded():
    builder = BarBuilder(_make_hist())
    assert "2330" in builder.symbols()
