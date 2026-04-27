from __future__ import annotations

import sys
from pathlib import Path

import shioaji as sj
from loguru import logger
from shioaji.constant import (
    Action,
    FuturesOCType,
    FuturesPriceType,
    OrderType,
    StockPriceType,
)

from monitor.config import Settings, load_settings


def _setup_logging() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO")


def show_version() -> None:
    _setup_logging()
    version = sj.__version__
    print(f"Shioaji Version: {version}")


def _login_with_ca(settings: Settings) -> sj.Shioaji:
    if not settings.shioaji_ca_path or not settings.shioaji_ca_password:
        raise RuntimeError(
            "Testing flow requires SHIOAJI_CA_PATH and SHIOAJI_CA_PASSWORD in config/.env"
        )
    if not settings.shioaji_person_id:
        raise RuntimeError("Testing flow requires SHIOAJI_PERSON_ID in config/.env")
    if not Path(settings.shioaji_ca_path).exists():
        raise RuntimeError(f"CA file not found: {settings.shioaji_ca_path}")

    api = sj.Shioaji(simulation=True)
    logger.info("Shioaji login (simulation=True)")
    api.login(
        api_key=settings.shioaji_api_key,
        secret_key=settings.shioaji_secret_key,
    )
    logger.info("Activate CA for person_id={}", settings.shioaji_person_id)
    activated = api.activate_ca(
        ca_path=settings.shioaji_ca_path,
        ca_passwd=settings.shioaji_ca_password,
        person_id=settings.shioaji_person_id,
    )
    if not activated:
        raise RuntimeError("CA activation returned False")
    logger.info("CA activated")
    return api


def testing_stock_ordering() -> None:
    _setup_logging()
    settings = load_settings()
    api = _login_with_ca(settings)
    try:
        contract = api.Contracts.Stocks["2890"]
        logger.info(
            "Stock contract loaded: {} {} reference={}",
            contract.code,
            contract.name,
            contract.reference,
        )
        order = sj.order.StockOrder(
            action=Action.Buy,
            price=contract.reference,
            quantity=1,
            price_type=StockPriceType.LMT,
            order_type=OrderType.ROD,
            account=api.stock_account,
        )
        trade = api.place_order(contract=contract, order=order)
        api.update_status()
        logger.info("Stock test order placed: status={} order_id={}",
                    trade.status.status, trade.order.id)
        print(trade)
    finally:
        try:
            api.logout()
        except Exception as exc:
            logger.warning("Shioaji logout failed: {}", exc)


def testing_futures_ordering() -> None:
    _setup_logging()
    settings = load_settings()
    api = _login_with_ca(settings)
    try:
        contract = api.Contracts.Futures["TXFR1"]
        logger.info(
            "Futures contract loaded: {} reference={}",
            contract.code,
            contract.reference,
        )
        order = sj.order.FuturesOrder(
            action=Action.Buy,
            price=contract.reference,
            quantity=1,
            price_type=FuturesPriceType.LMT,
            order_type=OrderType.ROD,
            octype=FuturesOCType.Auto,
            account=api.futopt_account,
        )
        trade = api.place_order(contract=contract, order=order)
        api.update_status()
        logger.info("Futures test order placed: status={} order_id={}",
                    trade.status.status, trade.order.id)
        print(trade)
    finally:
        try:
            api.logout()
        except Exception as exc:
            logger.warning("Shioaji logout failed: {}", exc)
