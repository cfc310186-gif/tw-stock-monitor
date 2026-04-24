from monitor.app import format_snapshots
from monitor.broker.shioaji_client import SnapshotRow


def test_format_snapshots_renders_row():
    rows = [
        SnapshotRow(
            code="2330",
            name="台積電",
            close=1145.0,
            change_price=10.0,
            change_rate=0.88,
            total_volume=23456,
        )
    ]
    out = format_snapshots(rows)
    assert "2330" in out
    assert "台積電" in out
    assert "1145.00" in out
    assert "+10.00" in out
    assert "+0.88%" in out
    assert "23,456" in out


def test_format_snapshots_negative_change():
    rows = [
        SnapshotRow(
            code="2317",
            name="鴻海",
            close=200.0,
            change_price=-1.5,
            change_rate=-0.74,
            total_volume=10000,
        )
    ]
    out = format_snapshots(rows)
    assert "-1.50" in out
    assert "-0.74%" in out
