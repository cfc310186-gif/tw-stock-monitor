from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
import shioaji as sj
from loguru import logger

from monitor.instruments import InstrumentType, kbar_windows

_TZ = "Asia/Taipei"


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

    # ------------------------------------------------------------------
    # Contract resolution
    # ------------------------------------------------------------------

    def _resolve_contract(self, symbol: str, itype: InstrumentType):
        if itype is InstrumentType.STOCK:
            return self._api.Contracts.Stocks[symbol]
        if itype is InstrumentType.DOMESTIC_FUTURES:
            return self._api.Contracts.Futures[symbol]
        if itype is InstrumentType.OVERSEAS_FUTURES:
            raise NotImplementedError(
                f"Overseas futures '{symbol}' is not supported by Shioaji's "
                "domestic API. Wire in a separate broker/data source for "
                "海外期貨 before adding it to the watchlist."
            )
        raise ValueError(f"Unknown instrument type: {itype}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def snapshots(self, instruments: dict[str, InstrumentType]) -> list[SnapshotRow]:
        """Fetch snapshot quotes for a {symbol: InstrumentType} mapping.

        Overseas-futures symbols are skipped with a warning (broker stub).
        """
        contracts = []
        user_by_code: dict[str, str] = {}     # contract.code → user-supplied symbol
        name_by_user: dict[str, str] = {}
        for sym, itype in instruments.items():
            try:
                contract = self._resolve_contract(sym, itype)
            except NotImplementedError as exc:
                logger.warning(str(exc))
                continue
            if contract is None:
                logger.warning("Unknown {} symbol, skipped: {}", itype.value, sym)
                continue
            contracts.append(contract)
            user_by_code[contract.code] = sym
            name_by_user[sym] = contract.name

        if not contracts:
            return []

        raw = self._api.snapshots(contracts)
        rows: list[SnapshotRow] = []
        for s in raw:
            user_sym = user_by_code.get(s.code, s.code)
            rows.append(
                SnapshotRow(
                    code=user_sym,
                    name=name_by_user.get(user_sym, ""),
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
        itype: InstrumentType,
        start: date | str,
        end: date | str,
    ) -> pd.DataFrame:
        """Fetch 1-min K bars and filter to the type-specific session window(s).

        Stocks → 09:00-13:30
        Domestic futures → day 08:45-13:45 + night 15:00-05:00
        Overseas futures → raises NotImplementedError (broker stub)
        """
        contract = self._resolve_contract(symbol, itype)
        if contract is None:
            raise ValueError(f"Unknown {itype.value} symbol: {symbol}")

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

        # Union of every session window for this instrument type. For
        # crossing-midnight windows (futures night session), SessionWindow
        # already handles the wrap.
        windows = kbar_windows(itype)
        mask = pd.Series(False, index=df.index)
        for w in windows:
            ts_time = df.index.time
            if w.start <= w.end:
                mask = mask | ((ts_time >= w.start) & (ts_time <= w.end))
            else:
                mask = mask | ((ts_time >= w.start) | (ts_time <= w.end))
        return df[mask]
