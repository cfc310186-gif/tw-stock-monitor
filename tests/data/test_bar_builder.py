from datetime import datetime

import pandas as pd
import pytest

from monitor.data.bar_builder import BarBuilder
from monitor.data.historical import TIMEFRAMES, resample_bars


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


def _walk_minutes(builder, *, day=(2024, 1, 3), start_minute=0, end_minute=6,
                  base_volume=1000, vol_per_min=100):
    """Drive the builder one tick per minute boundary on a given day.
    Returns {bar_min_just_closed: closed_list}."""
    from zoneinfo import ZoneInfo
    from datetime import datetime
    tz = ZoneInfo("Asia/Taipei")

    seed_ts = datetime(*day, 9, start_minute, 30, tzinfo=tz)
    builder.on_snapshot("2330", 100.0 + start_minute, base_volume, seed_ts)

    out = {}
    for m in range(start_minute + 1, end_minute + 1):
        ts = datetime(*day, 9, m, 0, tzinfo=tz)
        price = 100.0 + m
        vol = base_volume + (m - start_minute) * vol_per_min
        closed = builder.on_snapshot("2330", price, vol, ts)
        out[m - 1] = closed   # bar at minute (m-1) just closed
    return out


def test_5m_fires_only_on_multiples_of_5():
    """5m bar should close only when the just-closed 1m has minute % 5 == 0
    — i.e. minutes 0, 5 — and not on intermediate minutes 1..4."""
    builder = BarBuilder(_make_hist(n=60))
    closes = _walk_minutes(builder, end_minute=6)

    assert "5m" in closes[0]      # minute 0 closed → 09:00 5m bar
    assert "5m" not in closes[1]
    assert "5m" not in closes[2]
    assert "5m" not in closes[3]
    assert "5m" not in closes[4]  # was previously firing every minute
    assert "5m" in closes[5]      # minute 5 closed → 09:05 5m bar


def test_5m_bar_aggregates_minutes_1_through_5():
    """The 09:05 5m bar must contain 1m bars from minutes 1..5 — open from
    minute 1, close from minute 5, volume = sum of those five 1m volumes."""
    builder = BarBuilder(_make_hist(n=60))
    base_5m_len = len(builder.get_bars("2330", "5m"))

    _walk_minutes(builder, end_minute=6)
    df_5m = builder.get_bars("2330", "5m")

    # Two new 5m bars expected: 09:00 (singleton, just minute 0) and 09:05.
    assert len(df_5m) == base_5m_len + 2
    last = df_5m.iloc[-1]
    assert last["open"] == pytest.approx(101.0)    # minute 1's open
    assert last["close"] == pytest.approx(105.0)   # minute 5's close
    assert last["volume"] == 5 * 100               # sum of five 1m volumes


def test_15m_fires_only_on_multiples_of_15():
    builder = BarBuilder(_make_hist(n=60))
    closes = _walk_minutes(builder, end_minute=16)

    assert "15m" in closes[0]
    for m in (1, 5, 10, 14):
        assert "15m" not in closes[m]
    assert "15m" in closes[15]


def test_higher_tfs_do_not_double_close_per_minute():
    """Regression: previous logic fired 5m/15m/30m/60m every minute once
    the 1m deque had enough bars. After the fix, intermediate minutes
    produce no intraday coarser-timeframe closes (1d is excluded — it
    re-aggregates today's bar every minute by design)."""
    builder = BarBuilder(_make_hist(n=60))
    closes = _walk_minutes(builder, start_minute=10, end_minute=15)
    intraday = {"5m", "15m", "30m", "60m"}
    for m, tfs in closes.items():
        fired = intraday.intersection(tfs)
        if m == 10:
            assert fired == {"5m"}
        else:
            assert fired == set(), f"unexpected intraday closes at minute {m}: {tfs}"
