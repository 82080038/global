"""Tests for notifier — email notification functions."""

import os
from unittest.mock import patch


def test_email_not_configured():
    """When EMAIL_FROM is empty, email should be no-op."""
    with patch.dict(os.environ, {"EMAIL_FROM": "", "EMAIL_TO": "", "EMAIL_PASSWORD": ""}):
        from trading_system.utils.notifier import _email_configured
        assert not _email_configured()


def test_send_email_not_configured():
    """send_email should return False when not configured."""
    with patch.dict(os.environ, {"EMAIL_FROM": "", "EMAIL_TO": "", "EMAIL_PASSWORD": ""}):
        from trading_system.utils.notifier import send_email
        result = send_email("test subject", "test message")
        assert result is False
