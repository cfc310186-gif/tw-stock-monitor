from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv


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
    symbols: list[str]


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _optional(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


def load_watchlist(config_dir: Path | str = "config") -> list[str]:
    """Load symbols from watchlist.yaml; also loads .env so callers can read
    individual env vars without needing the full Shioaji/Telegram bundle."""
    config_dir = Path(config_dir)
    env_path = config_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    watchlist_path = config_dir / "watchlist.yaml"
    watchlist = yaml.safe_load(watchlist_path.read_text(encoding="utf-8"))
    symbols = [str(s) for s in watchlist.get("symbols", [])]
    if not symbols:
        raise RuntimeError(f"No symbols found in {watchlist_path}")
    return symbols


def load_settings(config_dir: Path | str = "config") -> Settings:
    symbols = load_watchlist(config_dir)
    return Settings(
        shioaji_api_key=_required("SHIOAJI_API_KEY"),
        shioaji_secret_key=_required("SHIOAJI_SECRET_KEY"),
        shioaji_ca_path=_optional("SHIOAJI_CA_PATH"),
        shioaji_ca_password=_optional("SHIOAJI_CA_PASSWORD"),
        shioaji_person_id=_optional("SHIOAJI_PERSON_ID"),
        shioaji_simulation=os.environ.get("SHIOAJI_SIMULATION", "false").lower() == "true",
        telegram_bot_token=_required("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_required("TELEGRAM_CHAT_ID"),
        symbols=symbols,
    )
