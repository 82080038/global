"""Unit tests for Component P: Email Notification (fallback)."""

from unittest.mock import MagicMock, patch

from trading_system.utils import notifier


class TestEmailConfig:
    def test_email_not_configured_by_default(self):
        with patch.object(notifier, "EMAIL_FROM", ""), patch.object(notifier, "EMAIL_TO", ""), patch.object(notifier, "EMAIL_PASSWORD", ""):
            assert not notifier._email_configured()

    def test_email_configured_when_all_set(self):
        with patch.object(notifier, "EMAIL_FROM", "a@b.com"), patch.object(notifier, "EMAIL_TO", "c@d.com"), patch.object(notifier, "EMAIL_PASSWORD", "pass"):
            assert notifier._email_configured()


class TestSendEmail:
    def test_send_email_not_configured(self):
        with patch.object(notifier, "EMAIL_FROM", ""), patch.object(notifier, "EMAIL_TO", ""), patch.object(notifier, "EMAIL_PASSWORD", ""):
            result = notifier.send_email("Test", "Body")
            assert result is False

    def test_send_email_success(self):
        mock_smtp = MagicMock()
        with patch.object(notifier, "EMAIL_FROM", "a@b.com"), patch.object(notifier, "EMAIL_TO", "c@d.com"), patch.object(notifier, "EMAIL_PASSWORD", "pass"), patch("smtplib.SMTP", return_value=mock_smtp):
            result = notifier.send_email("Test Subject", "Test Body")
            assert result is True
            mock_smtp.starttls.assert_called_once()
            mock_smtp.login.assert_called_once_with("a@b.com", "pass")
            mock_smtp.send_message.assert_called_once()
            mock_smtp.quit.assert_called_once()

    def test_send_email_smtp_error(self):
        mock_smtp = MagicMock()
        mock_smtp.login.side_effect = Exception("Auth failed")
        with patch.object(notifier, "EMAIL_FROM", "a@b.com"), patch.object(notifier, "EMAIL_TO", "c@d.com"), patch.object(notifier, "EMAIL_PASSWORD", "pass"), patch("smtplib.SMTP", return_value=mock_smtp):
            result = notifier.send_email("Test", "Body")
            assert result is False


class TestNotifyWithFallback:
    def test_fallback_uses_telegram_first(self):
        with patch.object(notifier, "send_telegram", return_value=True) as mock_tg, patch.object(notifier, "send_email", return_value=True) as mock_email:
            result = notifier.notify_with_fallback("test message")
            assert result is True
            mock_tg.assert_called_once_with("test message")
            mock_email.assert_not_called()

    def test_fallback_to_email_when_telegram_fails(self):
        with patch.object(notifier, "send_telegram", return_value=False) as mock_tg, patch.object(notifier, "send_email", return_value=True) as mock_email:
            result = notifier.notify_with_fallback("test message", subject="Alert")
            assert result is True
            mock_tg.assert_called_once()
            mock_email.assert_called_once_with("Alert", "test message")

    def test_fallback_all_fail(self):
        with patch.object(notifier, "send_telegram", return_value=False), patch.object(notifier, "send_email", return_value=False):
            result = notifier.notify_with_fallback("test message")
            assert result is False
