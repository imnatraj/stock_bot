from __future__ import annotations

from unittest.mock import patch

from stock_bot.integrations.telegram import format_signal_message, send_signal_alert


def test_format_message():
    msg = format_signal_message("RELIANCE", 1520, 1474, 1611)
    assert "RELIANCE" in msg
    assert "BUY: 1520.00" in msg


@patch("stock_bot.integrations.telegram.Bot.send_message")
def test_send_signal_alert(mock_send):
    # Ensure environment variables are set for the test
    import os

    os.environ["TELEGRAM_BOT_TOKEN"] = "fake-token"
    os.environ["TELEGRAM_CHAT_ID"] = "-10012345"
    mock_send.return_value = True
    ok = send_signal_alert("hello test")
    assert ok
