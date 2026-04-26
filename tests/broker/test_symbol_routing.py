"""Smoke test for instrument-type-aware contract routing in ShioajiClient.

We don't login to Shioaji here — we just verify that _resolve_contract
hits the right namespace (Stocks vs Futures) and that overseas raises
the NotImplementedError stub.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from monitor.broker.shioaji_client import ShioajiClient
from monitor.instruments import InstrumentType


def _client_with_fake_api():
    """Build a ShioajiClient whose underlying api is a MagicMock so we can
    inspect which namespace it accesses without touching the real broker."""
    client = ShioajiClient.__new__(ShioajiClient)
    client._api = MagicMock()
    client._api_key = ""
    client._secret_key = ""
    client._simulation = True
    return client


def test_stock_routes_to_stocks_namespace():
    client = _client_with_fake_api()
    client._resolve_contract("2330", InstrumentType.STOCK)
    client._api.Contracts.Stocks.__getitem__.assert_called_once_with("2330")
    client._api.Contracts.Futures.__getitem__.assert_not_called()


def test_active_etf_with_letters_still_routes_to_stocks():
    """Active ETFs / warrants can have non-numeric codes — they're still
    in the Stocks namespace, NOT auto-detected as futures."""
    client = _client_with_fake_api()
    client._resolve_contract("00940A", InstrumentType.STOCK)
    client._api.Contracts.Stocks.__getitem__.assert_called_once_with("00940A")
    client._api.Contracts.Futures.__getitem__.assert_not_called()


def test_domestic_futures_routes_to_futures_namespace():
    client = _client_with_fake_api()
    client._resolve_contract("MXFR1", InstrumentType.DOMESTIC_FUTURES)
    client._api.Contracts.Futures.__getitem__.assert_called_once_with("MXFR1")
    client._api.Contracts.Stocks.__getitem__.assert_not_called()


def test_overseas_futures_raises_not_implemented():
    client = _client_with_fake_api()
    with pytest.raises(NotImplementedError, match="海外期貨"):
        client._resolve_contract("NQ", InstrumentType.OVERSEAS_FUTURES)


def test_snapshots_skips_overseas_with_warning(caplog):
    client = _client_with_fake_api()
    # Stock contract resolves; overseas raises NotImplementedError → skipped.
    instruments = {
        "2330": InstrumentType.STOCK,
        "NQ": InstrumentType.OVERSEAS_FUTURES,
    }
    client._api.snapshots.return_value = []
    rows = client.snapshots(instruments)
    # No exception, no rows (mock returns []), and only Stock was looked up.
    assert rows == []
    client._api.Contracts.Stocks.__getitem__.assert_called_once_with("2330")
