from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

from monitor.instruments import InstrumentType


@dataclass(frozen=True)
class Settings:
    shioaji_api_key: str
    shioaji_secret_key: str
    shioaji_ca_path: str | None
    shioaji_ca_password: str | None
    shioaji_person_id: str | None
    shioaji_simulation: bool
    telegram_bot_token: str
    telegram_chat_id: str
    instruments: dict[str, InstrumentType]   # symbol → type
    # IB Gateway / TWS — only required when watchlist contains overseas_futures
    ib_host: str
    ib_port: int
    ib_client_id: int
    ib_readonly: bool
    ib_market_data_type: int
    ib_market_data_wait_seconds: float

    @property
    def symbols(self) -> list[str]:
        return list(self.instruments)

    def symbols_of(self, t: InstrumentType) -> list[str]:
        return [s for s, it in self.instruments.items() if it is t]

    @property
    def active_types(self) -> set[InstrumentType]:
        return set(self.instruments.values())


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _optional(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


# YAML key → InstrumentType mapping. Recognised aliases keep the config
# tolerant to plural/legacy forms.
_TYPE_KEYS: dict[str, InstrumentType] = {
    "stocks": InstrumentType.STOCK,
    "stock": InstrumentType.STOCK,
    "domestic_futures": InstrumentType.DOMESTIC_FUTURES,
    "futures": InstrumentType.DOMESTIC_FUTURES,
    "overseas_futures": InstrumentType.OVERSEAS_FUTURES,
}


def load_instruments(config_dir: Path | str = "config") -> dict[str, InstrumentType]:
    """Parse watchlist.yaml into a {symbol: InstrumentType} mapping.

    Also loads `.env` so callers that only need symbols (e.g. backtest --mock)
    don't have to repeat that work.
    """
    config_dir = Path(config_dir)
    env_path = config_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    watchlist_path = config_dir / "watchlist.yaml"
    raw = yaml.safe_load(watchlist_path.read_text(encoding="utf-8")) or {}

    instruments: dict[str, InstrumentType] = {}

    # Legacy flat-list form: { symbols: [...] } — assumed all stocks for
    # backwards compatibility with watchlists predating the type split.
    if "symbols" in raw:
        for sym in raw["symbols"] or []:
            instruments[str(sym)] = InstrumentType.STOCK

    # New grouped form: { stocks: [...], domestic_futures: [...], ... }
    for key, items in raw.items():
        if key == "symbols":
            continue
        if key not in _TYPE_KEYS:
            continue
        t = _TYPE_KEYS[key]
        for sym in items or []:
            instruments[str(sym)] = t

    if not instruments:
        raise RuntimeError(f"No symbols found in {watchlist_path}")
    return instruments


# Back-compat alias: returns just the symbol list (loses type info; prefer
# load_instruments() for any code that needs to route by instrument type).
def load_watchlist(config_dir: Path | str = "config") -> list[str]:
    return list(load_instruments(config_dir))


def load_settings(config_dir: Path | str = "config") -> Settings:
    instruments = load_instruments(config_dir)
    return Settings(
        shioaji_api_key=_required("SHIOAJI_API_KEY"),
        shioaji_secret_key=_required("SHIOAJI_SECRET_KEY"),
        shioaji_ca_path=_optional("SHIOAJI_CA_PATH"),
        shioaji_ca_password=_optional("SHIOAJI_CA_PASSWORD"),
        shioaji_person_id=_optional("SHIOAJI_PERSON_ID"),
        shioaji_simulation=os.environ.get("SHIOAJI_SIMULATION", "false").lower() == "true",
        telegram_bot_token=_required("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_required("TELEGRAM_CHAT_ID"),
        instruments=instruments,
        ib_host=os.environ.get("IB_HOST", "127.0.0.1"),
        ib_port=int(os.environ.get("IB_PORT", "4002")),       # 4002=Paper Gateway, 4001=Live
        ib_client_id=int(os.environ.get("IB_CLIENT_ID", "1")),
        ib_readonly=os.environ.get("IB_READONLY", "true").lower() == "true",
        ib_market_data_type=int(os.environ.get("IB_MARKET_DATA_TYPE", "1")),
        ib_market_data_wait_seconds=float(os.environ.get("IB_MARKET_DATA_WAIT_SECONDS", "10")),
    )
