from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger
from dotenv import load_dotenv

from monitor.broker.ib_client import IBClient
from monitor.config import load_instruments
from monitor.instruments import InstrumentType


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _load_env() -> None:
    env_path = Path("config") / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)


def main() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    _load_env()
    instruments = load_instruments()
    overseas = {
        sym: itype
        for sym, itype in instruments.items()
        if itype is InstrumentType.OVERSEAS_FUTURES
    }
    if not overseas:
        print("No overseas_futures symbols found in config/watchlist.yaml")
        sys.exit(1)

    host = os.environ.get("IB_HOST", "127.0.0.1")
    port = int(os.environ.get("IB_PORT", "4002"))
    client_id = int(os.environ.get("IB_CLIENT_ID", "1"))
    readonly = _env_bool("IB_READONLY", True)
    market_data_type = int(os.environ.get("IB_MARKET_DATA_TYPE", "1"))
    market_data_wait_seconds = float(os.environ.get("IB_MARKET_DATA_WAIT_SECONDS", "10"))

    logger.info(
        "IB quote check settings: host={}, port={}, clientId={}, readonly={}, "
        "marketDataType={}, wait={}s",
        host,
        port,
        client_id,
        readonly,
        market_data_type,
        market_data_wait_seconds,
    )

    client = IBClient(
        host=host,
        port=port,
        client_id=client_id,
        readonly=readonly,
        market_data_type=market_data_type,
        market_data_wait_seconds=market_data_wait_seconds,
    )

    client.login()
    try:
        rows = client.snapshots(overseas)
    finally:
        client.logout()

    if not rows:
        print("Connected to IB, but no quote rows were returned.")
        sys.exit(2)

    for row in rows:
        sign = "+" if row.change_price >= 0 else ""
        print(
            f"{row.code:10s} {row.name:16s} "
            f"{row.close:>10.2f} "
            f"{sign}{row.change_price:.2f} ({sign}{row.change_rate:.2f}%) "
            f"vol {row.total_volume:,}"
        )


if __name__ == "__main__":
    main()
