"""Composite broker client that dispatches by InstrumentType.

Stocks + domestic futures → ShioajiClient
Overseas futures            → IBClient (lazy-built; only if needed)

The public surface mirrors a single broker (login / logout / snapshots /
kbars) so app.py / historical.py / demo.py / backtest.cli don't need to
know multiple brokers exist.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

import pandas as pd
from loguru import logger

from monitor.broker.shioaji_client import ShioajiClient, SnapshotRow
from monitor.instruments import InstrumentType


class MultiBrokerClient:
    def __init__(
        self,
        shioaji: ShioajiClient | None = None,
        ib=None,   # IBClient — typed loose to avoid forcing ib_insync import
    ) -> None:
        self._brokers: dict[InstrumentType, object] = {}
        if shioaji is not None:
            self._brokers[InstrumentType.STOCK] = shioaji
            self._brokers[InstrumentType.DOMESTIC_FUTURES] = shioaji
        if ib is not None:
            self._brokers[InstrumentType.OVERSEAS_FUTURES] = ib

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def login(self) -> None:
        for broker in self._unique_brokers():
            broker.login()

    def logout(self) -> None:
        for broker in self._unique_brokers():
            try:
                broker.logout()
            except Exception as exc:
                logger.warning("Broker logout failed: {}", exc)

    def _unique_brokers(self):
        seen: list = []
        for broker in self._brokers.values():
            if broker not in seen:
                seen.append(broker)
        return seen

    # ------------------------------------------------------------------
    # Data API
    # ------------------------------------------------------------------

    def snapshots(self, instruments: dict[str, InstrumentType]) -> list[SnapshotRow]:
        # Group symbols by which broker handles them
        per_broker: dict[object, dict[str, InstrumentType]] = defaultdict(dict)
        for sym, itype in instruments.items():
            broker = self._brokers.get(itype)
            if broker is None:
                logger.warning("No broker for {} (symbol {}), skipped",
                               itype.value, sym)
                continue
            per_broker[broker][sym] = itype

        rows: list[SnapshotRow] = []
        for broker, group in per_broker.items():
            try:
                rows.extend(broker.snapshots(group))
            except Exception as exc:
                logger.warning("snapshots failed on {}: {}",
                               type(broker).__name__, exc)
        return rows

    def kbars(
        self,
        symbol: str,
        itype: InstrumentType,
        start: date | str,
        end: date | str,
    ) -> pd.DataFrame:
        broker = self._brokers.get(itype)
        if broker is None:
            raise NotImplementedError(
                f"No broker configured for {itype.value} — install IB extras "
                "and set IB_HOST/IB_PORT to enable overseas futures."
            )
        return broker.kbars(symbol, itype, start, end)
