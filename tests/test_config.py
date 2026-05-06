import pytest

from scrapper.config import Settings, load_settings


def test_load_settings_reads_all_four_env_vars(monkeypatch):
    monkeypatch.setenv("LUXMED_EMAIL", "a@b.pl")
    monkeypatch.setenv("LUXMED_PASSWORD", "secret123")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    settings = load_settings(load_dotenv_file=False)

    assert isinstance(settings, Settings)
    assert settings.luxmed_email == "a@b.pl"
    assert settings.luxmed_password == "secret123"
    assert settings.telegram_bot_token == "123:abc"
    assert settings.telegram_chat_id == "42"


def test_load_settings_missing_required_raises(monkeypatch):
    monkeypatch.delenv("LUXMED_EMAIL", raising=False)
    monkeypatch.delenv("LUXMED_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="LUXMED_EMAIL"):
        load_settings(load_dotenv_file=False)


def test_load_settings_telegram_optional(monkeypatch):
    monkeypatch.setenv("LUXMED_EMAIL", "a@b.pl")
    monkeypatch.setenv("LUXMED_PASSWORD", "x")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    settings = load_settings(load_dotenv_file=False)

    assert settings.telegram_bot_token is None
    assert settings.telegram_chat_id is None
