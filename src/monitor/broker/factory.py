"""Build the right broker client(s) based on what's in the watchlist.

If overseas futures are in scope, also creates an IBClient. The two
clients are wrapped in MultiBrokerClient so callers see a single object
with the familiar ShioajiClient interface.
"""
from __future__ import annotations

from monitor.broker.multi_client import MultiBrokerClient
from monitor.broker.shioaji_client import ShioajiClient
from monitor.instruments import InstrumentType


def build_client(settings) -> MultiBrokerClient:
    shioaji = ShioajiClient(
        api_key=settings.shioaji_api_key,
        secret_key=settings.shioaji_secret_key,
        simulation=settings.shioaji_simulation,
    )
    ib = None
    if InstrumentType.OVERSEAS_FUTURES in settings.active_types:
        # Lazy import — avoids requiring ib_insync when no overseas symbols.
        from monitor.broker.ib_client import IBClient
        ib = IBClient(
            host=settings.ib_host,
            port=settings.ib_port,
            client_id=settings.ib_client_id,
            readonly=settings.ib_readonly,
            market_data_type=settings.ib_market_data_type,
            market_data_wait_seconds=settings.ib_market_data_wait_seconds,
        )
    return MultiBrokerClient(shioaji=shioaji, ib=ib)
