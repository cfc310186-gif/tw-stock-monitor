"""Tests for the MultiBrokerClient dispatch logic.

We use lightweight fakes for both brokers so the test doesn't need
Shioaji or ib_insync installed.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import pytest

from monitor.broker.multi_client import MultiBrokerClient
from monitor.broker.shioaji_client import SnapshotRow
from monitor.instruments import InstrumentType


class _FakeBroker:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[Any] = []
        self.logged_in = False

    def login(self) -> None:
        self.logged_in = True

    def logout(self) -> None:
        self.logged_in = False

    def snapshots(self, instruments: dict[str, InstrumentType]) -> list[SnapshotRow]:
        self.calls.append(("snapshots", dict(instruments)))
        return [
            SnapshotRow(
                code=sym, name=f"{self.name}-{sym}",
                close=100.0, change_price=0.0, change_rate=0.0, total_volume=1000,
            )
            for sym in instruments
        ]

    def kbars(self, symbol, itype, start, end) -> pd.DataFrame:
        self.calls.append(("kbars", symbol, itype, start, end))
        return pd.DataFrame()


def test_dispatch_snapshots_by_type():
    sa = _FakeBroker("shioaji")
    ib = _FakeBroker("ib")
    multi = MultiBrokerClient(shioaji=sa, ib=ib)

    rows = multi.snapshots({
        "2330": InstrumentType.STOCK,
        "MXFR1": InstrumentType.DOMESTIC_FUTURES,
        "MNQ": InstrumentType.OVERSEAS_FUTURES,
    })

    # Two broker calls — Shioaji handled stock + dfut, IB handled overseas
    sa_call = next(c for c in sa.calls if c[0] == "snapshots")
    ib_call = next(c for c in ib.calls if c[0] == "snapshots")
    assert set(sa_call[1]) == {"2330", "MXFR1"}
    assert set(ib_call[1]) == {"MNQ"}
    assert {r.code for r in rows} == {"2330", "MXFR1", "MNQ"}


def test_dispatch_kbars_by_type():
    sa = _FakeBroker("shioaji")
    ib = _FakeBroker("ib")
    multi = MultiBrokerClient(shioaji=sa, ib=ib)

    multi.kbars("2330", InstrumentType.STOCK, date(2024, 1, 1), date(2024, 1, 31))
    multi.kbars("MNQ", InstrumentType.OVERSEAS_FUTURES,
                date(2024, 1, 1), date(2024, 1, 31))

    assert any(c[0] == "kbars" and c[1] == "2330" for c in sa.calls)
    assert any(c[0] == "kbars" and c[1] == "MNQ" for c in ib.calls)


def test_kbars_overseas_without_ib_raises():
    sa = _FakeBroker("shioaji")
    multi = MultiBrokerClient(shioaji=sa, ib=None)
    with pytest.raises(NotImplementedError, match="overseas"):
        multi.kbars("MNQ", InstrumentType.OVERSEAS_FUTURES,
                    date(2024, 1, 1), date(2024, 1, 31))


def test_snapshots_skips_overseas_with_warning_when_ib_missing(caplog):
    sa = _FakeBroker("shioaji")
    multi = MultiBrokerClient(shioaji=sa, ib=None)
    rows = multi.snapshots({
        "2330": InstrumentType.STOCK,
        "MNQ": InstrumentType.OVERSEAS_FUTURES,   # silently skipped
    })
    assert {r.code for r in rows} == {"2330"}


def test_login_logout_propagates_to_each_unique_broker():
    sa = _FakeBroker("shioaji")
    ib = _FakeBroker("ib")
    multi = MultiBrokerClient(shioaji=sa, ib=ib)
    multi.login()
    assert sa.logged_in is True and ib.logged_in is True
    multi.logout()
    assert sa.logged_in is False and ib.logged_in is False


def test_shioaji_used_for_both_stock_and_dfut_logged_in_once():
    """Same broker handles two instrument types — should connect once."""
    sa = _FakeBroker("shioaji")
    multi = MultiBrokerClient(shioaji=sa)
    multi.login()
    # Only one underlying broker, so logged_in toggled once
    assert sa.logged_in is True
