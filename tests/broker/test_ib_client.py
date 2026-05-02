"""Tests for IBClient that don't require ib_insync to be installed.

The ib_insync import inside `login()` is intercepted with a fake module
in sys.modules so we exercise the surrounding logic (front-month
selection, snapshot mapping) deterministically.
"""
from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from monitor.broker.ib_client import (
    _DEFAULT_EXCHANGE,
    _change_metrics,
    _pick_price,
    _split_symbol,
    IBClient,
)
from monitor.instruments import InstrumentType


# ---------------------------------------------------------------------------
# Pure-function helpers
# ---------------------------------------------------------------------------

def test_split_symbol_no_exchange():
    assert _split_symbol("MNQ") == ("MNQ", None)


def test_split_symbol_with_exchange_override():
    assert _split_symbol("NQ@CME") == ("NQ", "CME")


def test_default_exchange_known_micros():
    assert _DEFAULT_EXCHANGE["MNQ"] == "CME"
    assert _DEFAULT_EXCHANGE["MCL"] == "NYMEX"
    assert _DEFAULT_EXCHANGE["MGC"] == "COMEX"
    assert _DEFAULT_EXCHANGE["SIL"] == "COMEX"


def test_pick_price_prefers_last():
    t = SimpleNamespace(last=100.5, marketPrice=101.0, close=99.0,
                         bid=100.4, ask=100.6)
    assert _pick_price(t) == 100.5


def test_pick_price_falls_back_when_last_missing():
    t = SimpleNamespace(last=-1.0, marketPrice=101.0, close=99.0,
                         bid=100.4, ask=100.6)
    assert _pick_price(t) == 101.0


def test_pick_price_calls_market_price_method():
    t = SimpleNamespace(last=-1.0, marketPrice=lambda: 101.25, close=99.0)
    assert _pick_price(t) == 101.25


def test_pick_price_returns_none_when_all_invalid():
    t = SimpleNamespace(last=None, marketPrice=-1.0, close=0.0,
                         bid=None, ask=None)
    assert _pick_price(t) is None


def test_change_metrics_zero_when_no_prev_close():
    t = SimpleNamespace(close=None)
    assert _change_metrics(t, 100.0) == (0.0, 0.0)


def test_change_metrics_computes_diff_and_pct():
    t = SimpleNamespace(close=100.0)
    diff, pct = _change_metrics(t, 102.0)
    assert diff == pytest.approx(2.0)
    assert pct == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Front-month resolution (using a fake ib_insync.Future)
# ---------------------------------------------------------------------------

def _install_fake_ib_insync(monkeypatch):
    """Stub the IB shim so the module can be imported without the package.

    Provides a Future class compatible with the resolver call site. Stubs
    BOTH ib_async (preferred) and ib_insync (legacy fallback).
    """
    class _Future:
        def __init__(self, symbol="", exchange="", **kwargs):
            self.symbol = symbol
            self.exchange = exchange
            for k, v in kwargs.items():
                setattr(self, k, v)

    fake = types.ModuleType("ib_async")
    fake.IB = MagicMock
    fake.util = SimpleNamespace(startLoop=lambda: None, df=lambda bars: bars)
    fake.Future = _Future
    monkeypatch.setitem(sys.modules, "ib_async", fake)

    # Also pin ib_insync to the same module so legacy fallback works in
    # case some path tries it.
    monkeypatch.setitem(sys.modules, "ib_insync", fake)
    return fake


def _fake_contract(symbol, expiry, exchange, local=None):
    return SimpleNamespace(
        symbol=symbol,
        lastTradeDateOrContractMonth=expiry,
        exchange=exchange,
        localSymbol=local or f"{symbol}{expiry[2:6]}",
    )


def _fake_details(*contracts):
    return [SimpleNamespace(contract=c) for c in contracts]


def test_resolves_nearest_non_expired_contract(monkeypatch):
    _install_fake_ib_insync(monkeypatch)

    client = IBClient.__new__(IBClient)
    client._contracts = {}
    client._tickers = {}
    fake_ib = MagicMock()
    fake_ib.reqContractDetails.return_value = _fake_details(
        _fake_contract("MNQ", "20990101", "CME"),     # far future (sentinel)
        _fake_contract("MNQ", "20240101", "CME"),     # already expired (relative to now)
        _fake_contract("MNQ", "20991215", "CME"),     # later non-expired
    )
    client._ib = fake_ib

    contract = client._resolve_front_month("MNQ")
    # Earliest non-expired wins
    assert contract.lastTradeDateOrContractMonth == "20990101"
    assert contract.exchange == "CME"


def test_resolve_uses_default_exchange_for_known_symbols(monkeypatch):
    _install_fake_ib_insync(monkeypatch)

    client = IBClient.__new__(IBClient)
    client._contracts = {}
    client._tickers = {}
    client._ib = MagicMock()
    client._ib.reqContractDetails.return_value = _fake_details(
        _fake_contract("MGC", "20991215", "COMEX")
    )
    client._resolve_front_month("MGC")

    # Verify the Future passed to reqContractDetails has exchange=COMEX
    args, _ = client._ib.reqContractDetails.call_args
    assert args[0].exchange == "COMEX"
    assert args[0].symbol == "MGC"


def test_resolve_honours_exchange_override(monkeypatch):
    _install_fake_ib_insync(monkeypatch)

    client = IBClient.__new__(IBClient)
    client._contracts = {}
    client._tickers = {}
    client._ib = MagicMock()
    client._ib.reqContractDetails.return_value = _fake_details(
        _fake_contract("NQ", "20991215", "CME")
    )
    client._resolve_front_month("NQ@CME")

    args, _ = client._ib.reqContractDetails.call_args
    assert args[0].exchange == "CME"


def test_resolve_unknown_symbol_without_exchange_raises(monkeypatch):
    _install_fake_ib_insync(monkeypatch)
    client = IBClient.__new__(IBClient)
    client._contracts = {}
    client._tickers = {}
    client._ib = MagicMock()
    with pytest.raises(ValueError, match="No default exchange"):
        client._resolve_front_month("XYZUNKNOWN")


def test_snapshots_pumps_ib_loop_for_existing_tickers():
    client = IBClient.__new__(IBClient)
    client._contracts = {
        "MNQ": SimpleNamespace(localSymbol="MNQM6"),
    }
    client._tickers = {
        "MNQ": SimpleNamespace(last=100.0, close=99.0, volume=1234),
    }
    client._ib = MagicMock()

    rows = client.snapshots({"MNQ": InstrumentType.OVERSEAS_FUTURES})

    client._ib.sleep.assert_called_once_with(0)
    assert len(rows) == 1
    assert rows[0].code == "MNQ"
    assert rows[0].close == 100.0


def test_kbars_rejects_non_overseas_type():
    client = IBClient.__new__(IBClient)
    client._ib = MagicMock()
    with pytest.raises(ValueError, match="overseas"):
        client.kbars("2330", InstrumentType.STOCK, "2024-01-01", "2024-01-31")


def test_login_without_either_ib_module_raises_clear_error(monkeypatch):
    """If neither ib_async nor ib_insync is installed, login() should
    give a useful hint pointing at the [ib] extra."""
    saved_async = sys.modules.pop("ib_async", None)
    saved_insync = sys.modules.pop("ib_insync", None)
    monkeypatch.setitem(sys.modules, "ib_async", None)
    monkeypatch.setitem(sys.modules, "ib_insync", None)
    client = IBClient(host="127.0.0.1", port=4002)
    try:
        with pytest.raises(ImportError, match=r"\.\[ib\]"):
            client.login()
    finally:
        if saved_async is not None:
            sys.modules["ib_async"] = saved_async
        if saved_insync is not None:
            sys.modules["ib_insync"] = saved_insync
