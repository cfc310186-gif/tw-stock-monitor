"""Smoke tests that don't require Shioaji credentials or market hours."""
from monitor.broker.shioaji_client import SnapshotRow
from monitor.rules.base import Signal
from datetime import datetime
from zoneinfo import ZoneInfo


def test_snapshot_row_fields():
    row = SnapshotRow(
        code="2330",
        name="台積電",
        close=1145.0,
        change_price=10.0,
        change_rate=0.88,
        total_volume=23456,
    )
    assert row.code == "2330"
    assert row.close == 1145.0
    assert row.total_volume == 23456


def test_signal_dedup_key():
    ts = datetime(2024, 1, 2, 10, 5, tzinfo=ZoneInfo("Asia/Taipei"))
    sig = Signal(
        symbol="2330",
        rule_name="bb_reversal_5m",
        timeframe="5m",
        bar_close_time=ts,
        message="test",
    )
    key = sig.dedup_key()
    assert key == ("2330", "bb_reversal_5m", "5m", ts)
