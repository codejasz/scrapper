"""Telegram bot notifier — best-effort, nie blokuje flow."""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            resp = requests.post(
                url,
                json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"},
                timeout=10,
            )
            if not resp.ok:
                logger.warning("Telegram non-2xx: %s %s", resp.status_code, resp.text)
        except Exception as exc:  # ConnectionError, Timeout, etc.
            logger.warning("Telegram send failed: %s", exc)
