from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
import shioaji as sj
from loguru import logger

_TZ = "Asia/Taipei"

# Trading-hour windows for kbar filtering (Asia/Taipei).
# Stocks: regular session 09:00-13:30
# Futures (TXF/MXF/EXF): day session 08:45-13:45
_STOCK_HOURS = (pd.Timestamp("09:00").time(), pd.Timestamp("13:30").time())
_FUTURES_DAY_HOURS = (pd.Timestamp("08:45").time(), pd.Timestamp("13:45").time())


def is_futures_symbol(symbol: str) -> bool:
    """Stocks/ETFs are all-digit (e.g. '2330', '0050'); futures contain
    letters (e.g. 'MXFR1' for 小台連續近月, 'TXF202506')."""
    return not symbol.isdigit()


@dataclass(frozen=True)
class SnapshotRow:
    code: str
    name: str
    close: float
    change_price: float
    change_rate: float
    total_volume: int


class ShioajiClient:
    def __init__(self, api_key: str, secret_key: str, simulation: bool = False) -> None:
        self._api = sj.Shioaji(simulation=simulation)
        self._api_key = api_key
        self._secret_key = secret_key
        self._simulation = simulation

    def login(self) -> None:
        logger.info("Shioaji login (simulation={})", self._simulation)
        self._api.login(api_key=self._api_key, secret_key=self._secret_key)
        logger.info("Shioaji login OK")

    def logout(self) -> None:
        try:
            self._api.logout()
        except Exception as exc:
            logger.warning("Shioaji logout failed: {}", exc)

    def _resolve_contract(self, symbol: str):
        """Look up a stock or futures contract by symbol.

        Stocks: numeric code (e.g. '2330').
        Futures: any symbol containing letters (e.g. 'MXFR1' for 小台連續近月).
        """
        if is_futures_symbol(symbol):
            return self._api.Contracts.Futures[symbol]
        return self._api.Contracts.Stocks[symbol]

    def snapshots(self, symbols: list[str]) -> list[SnapshotRow]:
        contracts = []
        # Map contract.code → original user-supplied symbol so SnapshotRow.code
        # mirrors what the watchlist used (e.g. 'MXFR1') even if the broker
        # resolves the rolling alias to an underlying month-specific code.
        user_by_contract_code: dict[str, str] = {}
        name_by_user_sym: dict[str, str] = {}
        for sym in symbols:
            contract = self._resolve_contract(sym)
            if contract is None:
                logger.warning("Unknown symbol, skipped: {}", sym)
                continue
            contracts.append(contract)
            user_by_contract_code[contract.code] = sym
            name_by_user_sym[sym] = contract.name

        if not contracts:
            return []

        raw = self._api.snapshots(contracts)
        rows: list[SnapshotRow] = []
        for s in raw:
            user_sym = user_by_contract_code.get(s.code, s.code)
            rows.append(
                SnapshotRow(
                    code=user_sym,
                    name=name_by_user_sym.get(user_sym, ""),
                    close=float(s.close),
                    change_price=float(s.change_price),
                    change_rate=float(s.change_rate),
                    total_volume=int(s.total_volume),
                )
            )
        return rows

    def kbars(
        self,
        symbol: str,
        start: date | str,
        end: date | str,
    ) -> pd.DataFrame:
        """Fetch 1-min K bars for a stock or futures symbol.

        Returns a DataFrame indexed by tz-aware timestamp (Asia/Taipei) with
        columns: open, high, low, close, volume. Rows outside the symbol's
        regular trading window are excluded (stocks: 09:00-13:30; futures
        day session: 08:45-13:45).
        """
        contract = self._resolve_contract(symbol)
        if contract is None:
            raise ValueError(f"Unknown symbol: {symbol}")

        raw = self._api.kbars(contract, start=str(start), end=str(end))
        if not raw.ts:
            return pd.DataFrame(
                columns=["open", "high", "low", "close", "volume"]
            )

        ts = pd.to_datetime(raw.ts, unit="ns", utc=True).tz_convert(_TZ)
        df = pd.DataFrame(
            {
                "open": raw.Open,
                "high": raw.High,
                "low": raw.Low,
                "close": raw.Close,
                "volume": raw.Volume,
            },
            index=ts,
        )
        df.index.name = "ts"
        df = df.sort_index()

        start_t, end_t = _FUTURES_DAY_HOURS if is_futures_symbol(symbol) else _STOCK_HOURS
        mask = (df.index.time >= start_t) & (df.index.time <= end_t)
        return df[mask]
