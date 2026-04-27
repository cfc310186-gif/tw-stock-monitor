from __future__ import annotations

from typing import Callable

from monitor.indicators.atr import atr
from monitor.indicators.bbands import bbands
from monitor.indicators.donchian import donchian
from monitor.indicators.kd import kd
from monitor.indicators.ma import ema, sma
from monitor.indicators.macd import macd

INDICATORS: dict[str, Callable] = {
    "sma": sma,
    "ema": ema,
    "bbands": bbands,
    "kd": kd,
    "macd": macd,
    "donchian": donchian,
    "atr": atr,
}


def get(name: str) -> Callable:
    if name not in INDICATORS:
        raise KeyError(f"Unknown indicator: {name}. Available: {sorted(INDICATORS)}")
    return INDICATORS[name]
