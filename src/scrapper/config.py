"""Konfiguracja z .env. Telegram opcjonalny — bez niego notify wyłączony."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    luxmed_email: str
    luxmed_password: str
    telegram_bot_token: str | None
    telegram_chat_id: str | None

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


def load_settings(*, load_dotenv_file: bool = True, env_path: Path | None = None) -> Settings:
    if load_dotenv_file:
        load_dotenv(env_path)

    email = os.environ.get("LUXMED_EMAIL")
    password = os.environ.get("LUXMED_PASSWORD")
    if not email:
        raise RuntimeError("LUXMED_EMAIL nie ustawiony (sprawdź .env)")
    if not password:
        raise RuntimeError("LUXMED_PASSWORD nie ustawiony (sprawdź .env)")

    return Settings(
        luxmed_email=email,
        luxmed_password=password,
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN") or None,
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID") or None,
    )
