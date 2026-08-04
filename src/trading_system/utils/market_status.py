"""Market status utility — checks if IDX market is open/closed.

Uses the market_calendar table for holiday/trading-day info and
IDX trading hours (09:00–15:50 WIB / UTC+7) for intraday status.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from trading_system.data.storage import DataStorage

_WIB = ZoneInfo("Asia/Jakarta")

IDX_OPEN_HOUR = 9
IDX_OPEN_MINUTE = 0
IDX_CLOSE_HOUR = 15
IDX_CLOSE_MINUTE = 50

# Half-day close (e.g. before holidays) — typically 13:00 WIB
IDX_HALF_DAY_CLOSE_HOUR = 13
IDX_HALF_DAY_CLOSE_MINUTE = 0


def get_market_status(storage: DataStorage | None = None) -> dict:
    """Return current IDX market status.

    Returns:
        dict with keys:
            - is_open (bool): whether market is currently in trading session
            - is_trading_day (bool): whether today is a scheduled trading day
            - is_half_day (bool): whether today is a half-day session
            - holiday_name (str | None): holiday name if today is a holiday
            - current_time_wib (str): current time in WIB ISO format
            - open_time (str): market open time HH:MM WIB
            - close_time (str): market close time HH:MM WIB
            - next_open (str | None): next trading day date if market is closed
            - session (str): "pre_open", "open", "close", or "holiday"
    """
    if storage is None:
        storage = DataStorage()

    now_wib = datetime.now(_WIB)
    today_str = now_wib.strftime("%Y-%m-%d")

    # Query market_calendar for today
    row = None
    with storage._connect() as conn:
        row = conn.execute(
            "SELECT is_trading_day, holiday_name, half_day FROM market_calendar WHERE date = ?",
            (today_str,),
        ).fetchone()

    if row is None:
        # No calendar data for today — default to weekday check
        is_trading_day = now_wib.weekday() < 5  # Mon-Fri
        holiday_name = None
        is_half_day = False
    else:
        is_trading_day = bool(row[0])
        holiday_name = row[1]
        is_half_day = bool(row[2])

    # Determine close time for today
    if is_half_day:
        close_h, close_m = IDX_HALF_DAY_CLOSE_HOUR, IDX_HALF_DAY_CLOSE_MINUTE
    else:
        close_h, close_m = IDX_CLOSE_HOUR, IDX_CLOSE_MINUTE

    open_time_str = f"{IDX_OPEN_HOUR:02d}:{IDX_OPEN_MINUTE:02d}"
    close_time_str = f"{close_h:02d}:{close_m:02d}"

    # Determine session
    if not is_trading_day:
        session = "holiday"
        is_open = False
    else:
        current_minutes = now_wib.hour * 60 + now_wib.minute
        open_minutes = IDX_OPEN_HOUR * 60 + IDX_OPEN_MINUTE
        close_minutes = close_h * 60 + close_m

        if current_minutes < open_minutes:
            session = "pre_open"
            is_open = False
        elif current_minutes >= open_minutes and current_minutes < close_minutes:
            session = "open"
            is_open = True
        else:
            session = "close"
            is_open = False

    # Find next trading day if market is closed
    next_open = None
    if not is_open:
        next_open = _find_next_trading_day(storage, now_wib)

    # Determine mode: "trading" during market hours, "maintenance" otherwise
    if is_open:
        mode = "trading"
    else:
        mode = "maintenance"

    # Recommended actions per mode
    if mode == "trading":
        recommended_actions = [
            "Monitor positions & SL/TP",
            "Execute signals",
            "Track real-time prices",
        ]
    else:
        recommended_actions = [
            "Fetch & validate OHLCV data",
            "Compute analysis scores",
            "Generate recommendations",
            "Run backtests",
            "Update supplementary data",
        ]

    return {
        "is_open": is_open,
        "is_trading_day": is_trading_day,
        "is_half_day": is_half_day,
        "holiday_name": holiday_name,
        "current_time_wib": now_wib.isoformat(),
        "open_time": open_time_str,
        "close_time": close_time_str,
        "next_open": next_open,
        "session": session,
        "mode": mode,
        "recommended_actions": recommended_actions,
        "exchange": "IDX",
    }


def _find_next_trading_day(storage: DataStorage, from_date: datetime) -> str | None:
    """Find the next trading day after from_date (checks up to 30 days ahead)."""
    with storage._connect() as conn:
        for i in range(1, 31):
            check_date = (from_date + timedelta(days=i)).strftime("%Y-%m-%d")
            row = conn.execute(
                "SELECT is_trading_day FROM market_calendar WHERE date = ?",
                (check_date,),
            ).fetchone()
            if row is not None and row[0] == 1:
                return check_date
            # Fallback: if no calendar data, check weekday
            if row is None:
                check_dt = from_date + timedelta(days=i)
                if check_dt.weekday() < 5:
                    return check_date
    return None
