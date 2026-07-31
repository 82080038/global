"""Tests for notifier — Telegram notification functions."""

from unittest.mock import patch, MagicMock
import os


def test_notifier_not_configured():
    """When TELEGRAM_BOT_TOKEN is empty, notifier should be no-op."""
    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}):
        from trading_system.utils.notifier import _is_configured
        assert not _is_configured()


def test_send_telegram_no_token():
    """send_telegram should return False when not configured."""
    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}):
        from trading_system.utils.notifier import send_telegram
        result = send_telegram("test message")
        assert result is False
