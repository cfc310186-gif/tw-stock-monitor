from __future__ import annotations

import asyncio
import sys

from loguru import logger

from monitor.broker.shioaji_client import ShioajiClient, SnapshotRow
from monitor.config import load_settings
from monitor.notify.telegram import TelegramNotifier


def format_snapshots(rows: list[SnapshotRow]) -> str:
    lines = ["TW stock monitor — M1 smoke test", ""]
    for r in rows:
        sign = "+" if r.change_price >= 0 else ""
        lines.append(
            f"{r.code} {r.name}  {r.close:>8.2f}  "
            f"{sign}{r.change_price:.2f} ({sign}{r.change_rate:.2f}%)  "
            f"vol {r.total_volume:,}"
        )
    return "\n".join(lines)


async def _run() -> int:
    settings = load_settings()

    client = ShioajiClient(
        api_key=settings.shioaji_api_key,
        secret_key=settings.shioaji_secret_key,
        simulation=settings.shioaji_simulation,
    )
    notifier = TelegramNotifier(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )

    client.login()
    try:
        rows = client.snapshots(settings.symbols)
    finally:
        client.logout()

    if not rows:
        logger.error("No snapshots returned; check symbols / market hours")
        await notifier.send("M1 smoke test: no snapshot rows returned")
        return 1

    message = format_snapshots(rows)
    print(message)
    await notifier.send(message)
    return 0


def main() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
