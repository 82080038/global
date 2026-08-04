"""Notifier module — email notifications for trading signals.

Setup:
    1. Set environment variables in .env:
       - SMTP_SERVER (default: smtp.gmail.com)
       - SMTP_PORT (default: 587)
       - EMAIL_FROM
       - EMAIL_TO
       - EMAIL_PASSWORD

Usage:
    from trading_system.utils.notifier import send_email, notify_signal

    send_email("Trading Alert", "Hello from trading system!")
    notify_signal("BUY", "BBCA.JK", 8500, 78.5, {"stop_loss": 8200, "take_profit": 9000})
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Load .env file if it exists (simple parser, no dependency on python-dotenv)
_env_file = Path(__file__).resolve().parents[3] / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = value

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
EMAIL_FROM = os.getenv("EMAIL_FROM", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")


def _email_configured() -> bool:
    """Check if email credentials are set."""
    return bool(EMAIL_FROM and EMAIL_TO and EMAIL_PASSWORD)


def send_email(subject: str, body: str) -> bool:
    """Send an email notification via SMTP.

    Returns:
        True if sent successfully, False otherwise.
    """
    if not _email_configured():
        logger.info("Email not configured (EMAIL_FROM/EMAIL_TO/EMAIL_PASSWORD not set)")
        return False

    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart()
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()

        logger.info("Email notification sent successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


def notify_with_fallback(message: str, subject: str = "Trading System Alert") -> bool:
    """Send notification via email.

    Args:
        message: Message body text.
        subject: Email subject line.

    Returns:
        True if sent successfully, False otherwise.
    """
    return send_email(subject, message)


def notify_signal(
    action: str,
    ticker: str,
    price: float,
    conviction: float,
    details: dict | None = None,
) -> bool:
    """Send a formatted trading signal notification.

    Args:
        action: BUY, SELL, WATCHLIST, etc.
        ticker: Stock ticker (e.g. BBCA.JK).
        price: Current/entry price.
        conviction: Conviction score (0-100).
        details: Optional dict with stop_loss, take_profit, risk_flags, etc.

    Returns:
        True if sent successfully, False otherwise.
    """
    details = details or {}
    emoji = {"BUY": "🟢", "SELL": "🔴", "WATCHLIST": "🟡", "AVOID": "⚫"}.get(action, "🔔")

    lines = [
        f"{emoji} <b>SINYAL {action}</b>",
        f"📊 <b>{ticker}</b> @ Rp {price:,.0f}",
        f"🎯 Conviction: <b>{conviction:.1f}</b>",
    ]

    if "stop_loss" in details:
        sl = details["stop_loss"]
        lines.append(f"🛑 Stop Loss: Rp {sl:,.0f}" if isinstance(sl, (int, float)) else f"🛑 Stop Loss: {sl}")
    if "take_profit" in details:
        tp = details["take_profit"]
        lines.append(f"✅ Take Profit: Rp {tp:,.0f}" if isinstance(tp, (int, float)) else f"✅ Take Profit: {tp}")
    if "entry_price_range" in details:
        lines.append(f"📈 Entry Range: {details['entry_price_range']}")
    if details.get("risk_flags"):
        lines.append(f"⚠️ Risk Flags: {', '.join(details['risk_flags'])}")

    from datetime import datetime
    lines.append(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    message = "\n".join(lines)
    return send_email(f"SINYAL {action} — {ticker}", message)


def notify_risk_alert(ticker: str, alert_type: str, message: str) -> bool:
    """Send a risk alert notification (e.g. stop-loss hit, severe drawdown).

    Args:
        ticker: Stock ticker.
        alert_type: Type of alert (STOP_LOSS_HIT, SEVERE_DRAWDOWN, etc.).
        message: Alert details.

    Returns:
        True if sent successfully, False otherwise.
    """
    full_msg = f"RISK ALERT: {alert_type}\n{ticker}\n{message}"
    return send_email(f"RISK ALERT: {alert_type} — {ticker}", full_msg)
