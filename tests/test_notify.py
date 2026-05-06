import logging
from unittest.mock import MagicMock, patch

from scrapper.notify import TelegramNotifier


def test_send_calls_telegram_api_with_correct_payload():
    notifier = TelegramNotifier(bot_token="123:abc", chat_id="42")
    with patch("scrapper.notify.requests.post") as post:
        post.return_value = MagicMock(status_code=200, ok=True)
        notifier.send("Wizyta zarezerwowana")

    post.assert_called_once()
    url = post.call_args.args[0]
    assert "api.telegram.org/bot123:abc/sendMessage" in url
    payload = post.call_args.kwargs["json"]
    assert payload["chat_id"] == "42"
    assert payload["text"] == "Wizyta zarezerwowana"


def test_send_swallows_network_errors_and_logs(caplog):
    notifier = TelegramNotifier(bot_token="t", chat_id="c")
    with patch("scrapper.notify.requests.post") as post:
        post.side_effect = ConnectionError("brak netu")
        with caplog.at_level(logging.WARNING, logger="scrapper.notify"):
            notifier.send("hello")

    assert any("Telegram" in r.getMessage() for r in caplog.records)


def test_send_logs_warning_on_non_200(caplog):
    notifier = TelegramNotifier(bot_token="t", chat_id="c")
    with patch("scrapper.notify.requests.post") as post:
        post.return_value = MagicMock(status_code=400, ok=False, text="bad")
        with caplog.at_level(logging.WARNING, logger="scrapper.notify"):
            notifier.send("hello")  # should NOT raise

    assert any("Telegram" in r.getMessage() for r in caplog.records)
