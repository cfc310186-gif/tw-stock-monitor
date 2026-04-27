"""Tests for the type-aware watchlist parser."""
from __future__ import annotations

from pathlib import Path

import pytest

from monitor.config import load_instruments, load_watchlist
from monitor.instruments import InstrumentType


def _write(tmp_path: Path, content: str) -> Path:
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "watchlist.yaml").write_text(content, encoding="utf-8")
    return cfg


def test_grouped_watchlist(tmp_path):
    cfg = _write(tmp_path, """
stocks:
  - "2330"
  - "0050"
domestic_futures:
  - "MXFR1"
overseas_futures:
  - "NQ"
""")
    inst = load_instruments(cfg)
    assert inst == {
        "2330": InstrumentType.STOCK,
        "0050": InstrumentType.STOCK,
        "MXFR1": InstrumentType.DOMESTIC_FUTURES,
        "NQ": InstrumentType.OVERSEAS_FUTURES,
    }


def test_legacy_flat_list_treated_as_stocks(tmp_path):
    cfg = _write(tmp_path, """
symbols:
  - "2330"
  - "0050"
""")
    inst = load_instruments(cfg)
    assert inst == {
        "2330": InstrumentType.STOCK,
        "0050": InstrumentType.STOCK,
    }


def test_active_etf_with_letters_routes_to_stocks(tmp_path):
    cfg = _write(tmp_path, """
stocks:
  - "00940A"
  - "081234"
""")
    inst = load_instruments(cfg)
    assert inst["00940A"] is InstrumentType.STOCK
    assert inst["081234"] is InstrumentType.STOCK


def test_load_watchlist_returns_just_symbols(tmp_path):
    cfg = _write(tmp_path, """
stocks: ["2330"]
domestic_futures: ["MXFR1"]
""")
    syms = load_watchlist(cfg)
    assert set(syms) == {"2330", "MXFR1"}


def test_empty_watchlist_raises(tmp_path):
    cfg = _write(tmp_path, "stocks: []\n")
    with pytest.raises(RuntimeError, match="No symbols"):
        load_instruments(cfg)
