"""Smoke test for stock-vs-futures symbol routing in ShioajiClient."""
from monitor.broker.shioaji_client import is_futures_symbol


def test_stocks_and_etfs_are_not_futures():
    assert is_futures_symbol("2330") is False    # 台積電
    assert is_futures_symbol("0050") is False    # 元大台灣50 ETF
    assert is_futures_symbol("2317") is False
    assert is_futures_symbol("9999") is False


def test_taiex_futures_aliases():
    assert is_futures_symbol("TXFR1") is True    # 大台連續近月
    assert is_futures_symbol("MXFR1") is True    # 小台連續近月
    assert is_futures_symbol("TXFR2") is True    # 次月
    assert is_futures_symbol("EXFR1") is True    # 電子期


def test_specific_month_futures():
    assert is_futures_symbol("TXF202506") is True
    assert is_futures_symbol("MXF202412") is True
