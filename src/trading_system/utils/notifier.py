"""Notifier module — Telegram bot integration for real-time trading signals.

Setup:
    1. Create a Telegram bot via @BotFather, get the bot token.
    2. Get your chat ID (message @userinfobot or use the bot's getUpdates API).
    3. Set environment variables:
       - TELEGRAM_BOT_TOKEN
       - TELEGRAM_CHAT_ID
    4. Or set them in a .env file at project root.

Usage:
    from trading_system.utils.notifier import send_telegram, notify_signal

    send_telegram("Hello from trading system!")
    notify_signal("BUY", "BBCA.JK", 8500, 78.5, {"stop_loss": 8200, "take_profit": 9000})
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

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

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def _is_configured() -> bool:
    """Check if Telegram credentials are set."""
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def send_telegram(message: str, parse_mode: str | None = None) -> bool:
    """Send a message via Telegram bot.

    Args:
        message: Text to send.
        parse_mode: Optional 'HTML' or 'Markdown' for formatted messages.

    Returns:
        True if sent successfully, False otherwise.
    """
    if not _is_configured():
        logger.info("Telegram not configured (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set)")
        return False

    try:
        import requests

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info("Telegram message sent successfully")
            return True
        else:
            logger.error(f"Telegram API error: {resp.status_code} — {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


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
    return send_telegram(message, parse_mode="HTML")


def notify_risk_alert(ticker: str, alert_type: str, message: str) -> bool:
    """Send a risk alert notification (e.g. stop-loss hit, severe drawdown).

    Args:
        ticker: Stock ticker.
        alert_type: Type of alert (STOP_LOSS_HIT, SEVERE_DRAWDOWN, etc.).
        message: Alert details.

    Returns:
        True if sent successfully, False otherwise.
    """
    full_msg = f"⚠️ <b>RISK ALERT: {alert_type}</b>\n📊 {ticker}\n{message}"
    return send_telegram(full_msg, parse_mode="HTML")
