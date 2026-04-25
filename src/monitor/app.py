from __future__ import annotations

import asyncio
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from loguru import logger

from monitor import scheduler
from monitor.broker.shioaji_client import ShioajiClient
from monitor.config import load_settings
from monitor.data.bar_builder import BarBuilder
from monitor.data.historical import load_history
from monitor.data.store import SignalStore
from monitor.notify.telegram import TelegramNotifier
from monitor.rules.engine import RuleEngine

_TZ = ZoneInfo("Asia/Taipei")
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_RULES_YAML = _PROJECT_ROOT / "config" / "rules.yaml"
_DEFAULT_DB_PATH = _PROJECT_ROOT / "signals.db"
_POLL_INTERVAL = 20
_RECONNECT_DELAYS = [2, 4, 8, 16, 32]


def _rules_path() -> Path:
    return Path(os.environ.get("MONITOR_RULES_PATH") or _DEFAULT_RULES_YAML)


def _db_path() -> Path:
    return Path(os.environ.get("MONITOR_DB_PATH") or _DEFAULT_DB_PATH)


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def _bootstrap(client: ShioajiClient, settings) -> BarBuilder:
    logger.info("Bootstrapping {} symbols…", len(settings.symbols))
    hist = load_history(client, settings.symbols, lookback_days=60)
    if not hist:
        raise RuntimeError("No historical data loaded (simulation outside trading hours?)")
    logger.info("Bootstrap done: {} symbols", len(hist))
    return BarBuilder(hist)


def _restore_engine(engine: RuleEngine, store: SignalStore) -> None:
    since = datetime.now(_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    keys = store.recent_dedup_keys(since)
    engine._seen.update(keys)
    if keys:
        logger.info("Restored {} dedup keys from DB", len(keys))


# ---------------------------------------------------------------------------
# Polling loop
# ---------------------------------------------------------------------------

async def _poll_once(client, builder, engine, store, notifier, settings) -> None:
    now = datetime.now(_TZ)
    rows = client.snapshots(settings.symbols)
    for row in rows:
        closed_tfs = builder.on_snapshot(row.code, row.close, row.total_volume, now)
        for tf in closed_tfs:
            bars = builder.get_bars(row.code, tf)
            signals = engine.evaluate(row.code, tf, bars, now=now)
            for sig in signals:
                logger.info("🔔 {} {} {}", sig.symbol, sig.rule_name, sig.timeframe)
                if store.save(sig, triggered_at=now):
                    await notifier.send(sig.message)


async def _run_market_session(
    client, builder, engine, store, notifier, settings,
    stop_event: asyncio.Event,
) -> None:
    logger.info("Market open — polling every {}s", _POLL_INTERVAL)
    errors = 0

    while scheduler.is_market_open() and not stop_event.is_set():
        try:
            await _poll_once(client, builder, engine, store, notifier, settings)
            errors = 0
        except Exception as exc:
            errors += 1
            delay = _RECONNECT_DELAYS[min(errors - 1, len(_RECONNECT_DELAYS) - 1)]
            logger.warning("Poll error #{} — retry in {}s: {}", errors, delay, exc)
            await _sleep_or_stop(delay, stop_event)
            continue

        remaining = scheduler.seconds_until_close()
        await _sleep_or_stop(min(_POLL_INTERVAL, remaining + 1), stop_event)

    if stop_event.is_set():
        logger.info("Stop signal received — exiting market loop")
    else:
        logger.info("Market closed at {}", datetime.now(_TZ).strftime("%H:%M"))


async def _sleep_or_stop(seconds: float, stop_event: asyncio.Event) -> None:
    """Sleep for `seconds` but wake immediately on stop signal."""
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def _run() -> int:
    settings = load_settings()
    store = SignalStore(_db_path())
    notifier = TelegramNotifier(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )
    engine = RuleEngine.from_yaml(_rules_path())

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig_name in ("SIGINT", "SIGTERM"):
        try:
            loop.add_signal_handler(getattr(signal, sig_name), stop_event.set)
        except (NotImplementedError, AttributeError):
            pass  # Windows lacks add_signal_handler for SIGTERM

    if not scheduler.is_trading_day():
        logger.info("Not a trading day — exiting")
        store.close()
        return 0

    wait = scheduler.seconds_until_open()
    if wait > 0:
        logger.info("Market opens in {:.0f} min — waiting…", wait / 60)
        await _sleep_or_stop(wait, stop_event)
        if stop_event.is_set():
            logger.info("Stop signal received during pre-open wait — exiting")
            store.close()
            return 0

    client = ShioajiClient(
        api_key=settings.shioaji_api_key,
        secret_key=settings.shioaji_secret_key,
        simulation=settings.shioaji_simulation,
    )
    client.login()
    try:
        builder = _bootstrap(client, settings)
        _restore_engine(engine, store)
        await notifier.send(
            f"✅ monitor 啟動\n"
            f"監測 {len(settings.symbols)} 檔\n"
            f"規則: {[r.name for r in engine._rules]}"
        )
        await _run_market_session(
            client, builder, engine, store, notifier, settings, stop_event,
        )
        await notifier.send("🔕 monitor 收盤停止")
    except Exception as exc:
        logger.exception("Fatal: {}", exc)
        try:
            await notifier.send(f"⚠️ monitor 錯誤: {exc}")
        except Exception:
            pass
        return 1
    finally:
        client.logout()
        store.close()

    return 0


def main() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    logger.add("monitor.log", rotation="1 day", retention="7 days",
                level="DEBUG", encoding="utf-8")
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
