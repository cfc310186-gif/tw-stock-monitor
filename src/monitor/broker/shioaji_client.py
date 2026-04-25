from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
import shioaji as sj
from loguru import logger

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

    def snapshots(self, symbols: list[str]) -> list[SnapshotRow]:
        contracts = []
        name_by_code: dict[str, str] = {}
        for sym in symbols:
            contract = self._api.Contracts.Stocks[sym]
            if contract is None:
                logger.warning("Unknown symbol, skipped: {}", sym)
                continue
            contracts.append(contract)
            name_by_code[contract.code] = contract.name

        if not contracts:
            return []

        raw = self._api.snapshots(contracts)
        rows: list[SnapshotRow] = []
        for s in raw:
            rows.append(
                SnapshotRow(
                    code=s.code,
                    name=name_by_code.get(s.code, ""),
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
        """Fetch 1-min K bars for a stock symbol.

        Returns a DataFrame indexed by tz-aware timestamp (Asia/Taipei) with
        columns: open, high, low, close, volume.
        Rows outside 09:00–13:30 are excluded.
        """
        contract = self._api.Contracts.Stocks[symbol]
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

        start_t = pd.Timestamp("09:00").time()
        end_t = pd.Timestamp("13:30").time()
        mask = (df.index.time >= start_t) & (df.index.time <= end_t)
        return df[mask]
