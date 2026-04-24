from __future__ import annotations

from loguru import logger
from telegram import Bot


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot = Bot(token=bot_token)
        self._chat_id = chat_id

    async def send(self, text: str) -> None:
        preview = text.replace("\n", " | ")
        logger.debug("Telegram send: {}", preview)
        await self._bot.send_message(chat_id=self._chat_id, text=text)
