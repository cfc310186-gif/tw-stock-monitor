"""Interactive Brokers data client for overseas futures.

Mirrors the public surface of ShioajiClient (login / logout / snapshots /
kbars) so the rest of the pipeline can stay broker-agnostic.

Only used for InstrumentType.OVERSEAS_FUTURES. Lazy-imports ib_insync so
non-IB users don't need it installed.

Connection model
----------------
ib_insync requires a local IB Gateway or TWS process to be running. The
Python client connects via socket:
  Paper: 127.0.0.1:4002 (Gateway) or 7497 (TWS)
  Live:  127.0.0.1:4001 (Gateway) or 7496 (TWS)

Default uses Paper Gateway (4002).

Continuous-contract resolution
------------------------------
The watchlist holds bare symbols ('MNQ', 'MCL', …). At login we call
reqContractDetails() with no expiry, sort the returned month contracts
by expiry, and pick the nearest non-expired one. SnapshotRow.code maps
the resolved contract back to the watchlist symbol so downstream code
sees a stable identifier even when rolls happen.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd
from loguru import logger

from monitor.broker.shioaji_client import SnapshotRow
from monitor.instruments import InstrumentType

# Default exchange routing for the most common micro futures. Users can
# override per-symbol in the watchlist using the "SYMBOL@EXCHANGE" form
# (parsed by _split_symbol below).
_DEFAULT_EXCHANGE: dict[str, str] = {
    # CME — Equity index micros
    "MNQ": "CME",   # Micro E-mini Nasdaq-100
    "MES": "CME",   # Micro E-mini S&P 500
    "M2K": "CME",   # Micro E-mini Russell 2000
    "MYM": "CBOT",  # Micro E-mini Dow
    # CME — FX, BTC
    "MBT": "CME",   # Micro Bitcoin
    # NYMEX — Energy micros
    "MCL": "NYMEX", # Micro WTI Crude Oil
    "MNG": "NYMEX", # Micro Henry Hub Natural Gas
    # COMEX — Metal micros
    "MGC": "COMEX", # Micro Gold
    "SIL": "COMEX", # Silver MINI 1000 oz
}


def _split_symbol(raw: str) -> tuple[str, str | None]:
    """'MNQ' → ('MNQ', None); 'MNQ@CME' → ('MNQ', 'CME')."""
    if "@" in raw:
        sym, ex = raw.split("@", 1)
        return sym.strip(), ex.strip()
    return raw.strip(), None


class IBClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 1,
        readonly: bool = True,
        market_data_type: int = 1,   # 1=Live, 3=Delayed, 4=Delayed-Frozen
    ) -> None:
        self._host = host
        self._port = port
        self._client_id = client_id
        self._readonly = readonly
        self._market_data_type = market_data_type
        self._ib: Any = None  # set on login()
        self._contracts: dict[str, Any] = {}     # user_sym -> qualified Contract
        self._tickers: dict[str, Any] = {}       # user_sym -> live Ticker

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def login(self) -> None:
        # Python 3.12+ removed implicit event-loop creation. eventkit (used
        # by ib_insync) touches the loop at import time, so create one first.
        import asyncio
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        # Prefer ib_async (maintained fork that fixes Python 3.12+ compat);
        # fall back to legacy ib_insync if only that is installed.
        try:
            from ib_async import IB, util
        except ImportError:
            try:
                from ib_insync import IB, util
            except ImportError as exc:
                raise ImportError(
                    "Neither ib_async nor ib_insync is installed. Run "
                    "`pip install -e \".[ib]\"` (installs ib_async, the "
                    "actively-maintained fork)."
                ) from exc

        util.startLoop()  # patch the asyncio loop so sync calls work inline
        self._ib = IB()
        logger.info("IB connect {}:{} (clientId={}, readonly={})",
                    self._host, self._port, self._client_id, self._readonly)
        self._ib.connect(self._host, self._port,
                         clientId=self._client_id, readonly=self._readonly)
        self._ib.reqMarketDataType(self._market_data_type)
        logger.info("IB connected")

    def logout(self) -> None:
        if self._ib is None:
            return
        try:
            for contract in self._contracts.values():
                try:
                    self._ib.cancelMktData(contract)
                except Exception:
                    pass
            self._ib.disconnect()
        except Exception as exc:
            logger.warning("IB disconnect failed: {}", exc)

    # ------------------------------------------------------------------
    # Contract resolution (continuous → front-month)
    # ------------------------------------------------------------------

    def _resolve_front_month(self, raw_symbol: str):
        """Pick the nearest non-expired contract for `raw_symbol`.

        Cached after first call. Watchlist may use bare symbol (lookup via
        `_DEFAULT_EXCHANGE`) or `SYMBOL@EXCHANGE` for explicit routing.
        """
        if raw_symbol in self._contracts:
            return self._contracts[raw_symbol]

        try:
            from ib_async import Future
        except ImportError:
            from ib_insync import Future

        sym, ex_override = _split_symbol(raw_symbol)
        exchange = ex_override or _DEFAULT_EXCHANGE.get(sym)
        if exchange is None:
            raise ValueError(
                f"No default exchange for '{sym}'. Use '{sym}@<EXCHANGE>' "
                "in the watchlist (e.g. 'MNQ@CME')."
            )

        # No expiry → IB returns every listed month for this product.
        details = self._ib.reqContractDetails(
            Future(symbol=sym, exchange=exchange)
        )
        if not details:
            raise ValueError(f"No IB contract found for {sym} on {exchange}")

        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        valid = [d for d in details
                 if d.contract.lastTradeDateOrContractMonth >= today]
        if not valid:
            raise ValueError(f"All {sym} contracts expired (today={today})")

        front = min(valid,
                    key=lambda d: d.contract.lastTradeDateOrContractMonth)
        contract = front.contract
        logger.info("IB resolved {} → {} (expiry {}, exchange {})",
                    raw_symbol, contract.localSymbol,
                    contract.lastTradeDateOrContractMonth, contract.exchange)
        self._contracts[raw_symbol] = contract
        return contract

    # ------------------------------------------------------------------
    # Public data API (mirrors ShioajiClient)
    # ------------------------------------------------------------------

    def snapshots(self, instruments: dict[str, InstrumentType]) -> list[SnapshotRow]:
        """Return SnapshotRow per overseas-futures symbol.

        Non-overseas symbols in the input are silently skipped (handled by
        another broker). Live tickers are kept open across polls; this
        method just reads the current values.
        """
        rows: list[SnapshotRow] = []
        for raw_sym, itype in instruments.items():
            if itype is not InstrumentType.OVERSEAS_FUTURES:
                continue
            try:
                contract = self._resolve_front_month(raw_sym)
            except Exception as exc:
                logger.warning("IB resolve failed for {}: {}", raw_sym, exc)
                continue

            ticker = self._tickers.get(raw_sym)
            if ticker is None:
                ticker = self._ib.reqMktData(contract, "", False, False)
                self._tickers[raw_sym] = ticker
                self._ib.sleep(2)   # let the first tick arrive

            close = _pick_price(ticker)
            if close is None:
                logger.warning("IB no live price yet for {}, skipping", raw_sym)
                continue

            change_price, change_rate = _change_metrics(ticker, close)
            rows.append(
                SnapshotRow(
                    code=raw_sym,
                    name=contract.localSymbol or raw_sym,
                    close=float(close),
                    change_price=float(change_price),
                    change_rate=float(change_rate),
                    total_volume=int(ticker.volume or 0),
                )
            )
        return rows

    def kbars(
        self,
        symbol: str,
        itype: InstrumentType,
        start: date | str,
        end: date | str,
    ) -> pd.DataFrame:
        if itype is not InstrumentType.OVERSEAS_FUTURES:
            raise ValueError(f"IBClient only handles overseas futures, got {itype}")
        try:
            from ib_async import util
        except ImportError:
            from ib_insync import util

        contract = self._resolve_front_month(symbol)

        # IB's reqHistoricalData uses a duration string, not a start/end pair.
        # Convert the date range into a duration that covers it.
        if isinstance(end, str):
            end_dt = pd.Timestamp(end)
        else:
            end_dt = pd.Timestamp(end)
        if isinstance(start, str):
            start_dt = pd.Timestamp(start)
        else:
            start_dt = pd.Timestamp(start)
        days = max(1, (end_dt - start_dt).days)

        end_str = end_dt.strftime("%Y%m%d-%H:%M:%S") if end_dt.time() != pd.Timestamp(0).time() else ""
        bars = self._ib.reqHistoricalData(
            contract,
            endDateTime=end_str,
            durationStr=f"{days} D",
            barSizeSetting="1 min",
            whatToShow="TRADES",
            useRTH=False,        # include extended/overnight hours
            formatDate=2,        # epoch UTC
            keepUpToDate=False,
        )
        if not bars:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = util.df(bars)
        # ib_insync returns columns date|open|high|low|close|volume|average|barCount
        df = df.rename(columns={"date": "ts"})
        df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert("Asia/Taipei")
        df = df.set_index("ts")[["open", "high", "low", "close", "volume"]]
        df.index.name = "ts"
        df = df.sort_index()
        # No session filter — overseas-futures session covers ~24h
        return df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pick_price(ticker) -> float | None:
    """Pick a sensible 'last' price even when last tick is missing."""
    for attr in ("last", "marketPrice", "close", "bid", "ask"):
        v = getattr(ticker, attr, None)
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        # IB sometimes returns -1 / NaN for absent values
        if v > 0 and v == v:
            return v
    return None


def _change_metrics(ticker, last: float) -> tuple[float, float]:
    """Return (change_price, change_rate) vs prior close, defaulting to 0."""
    prev = getattr(ticker, "close", None)  # IB 'close' attr = previous-day close
    try:
        prev = float(prev) if prev is not None else None
    except (TypeError, ValueError):
        prev = None
    if not prev or prev <= 0:
        return 0.0, 0.0
    diff = last - prev
    return diff, (diff / prev) * 100.0
