from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import text

from app.database.connection import get_engine


@dataclass(frozen=True)
class ExchangeWindow:
    exchange: str
    timezone: str
    open_time: time
    safe_close_time: time


EXCHANGE_WINDOWS = {
    "NASDAQ": ExchangeWindow(
        exchange="NASDAQ",
        timezone="America/New_York",
        open_time=time(9, 30),
        safe_close_time=time(16, 30),
    ),
    "NYSE": ExchangeWindow(
        exchange="NYSE",
        timezone="America/New_York",
        open_time=time(9, 30),
        safe_close_time=time(16, 30),
    ),
    "Euronext Amsterdam": ExchangeWindow(
        exchange="Euronext Amsterdam",
        timezone="Europe/Amsterdam",
        open_time=time(9, 0),
        safe_close_time=time(17, 45),
    ),
    "KRX": ExchangeWindow(
        exchange="KRX",
        timezone="Asia/Seoul",
        open_time=time(9, 0),
        safe_close_time=time(15, 45),
    ),
}


def active_security_exchanges(engine=None) -> list[str]:
    if engine is None:
        engine = get_engine()

    exchanges = pd.read_sql(
        text("""
            SELECT DISTINCT exchange
            FROM securities
            WHERE active = TRUE
              AND exchange IS NOT NULL
            ORDER BY exchange
        """),
        engine,
    )

    return exchanges["exchange"].dropna().tolist()


def _is_exchange_open(window: ExchangeWindow, now_utc: datetime) -> bool:
    local_now = now_utc.astimezone(ZoneInfo(window.timezone))

    if local_now.weekday() >= 5:
        return False

    local_time = local_now.time()
    return window.open_time <= local_time < window.safe_close_time


def market_sync_blockers(
    exchanges: list[str],
    now_utc: datetime | None = None,
) -> list[str]:
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    else:
        now_utc = now_utc.astimezone(timezone.utc)

    blockers = []

    for exchange in sorted(set(exchanges)):
        window = EXCHANGE_WINDOWS.get(exchange)
        if window is None:
            blockers.append(f"{exchange}: unknown trading hours")
            continue

        if _is_exchange_open(window, now_utc):
            local_now = now_utc.astimezone(ZoneInfo(window.timezone))
            blockers.append(
                f"{exchange}: open until {window.safe_close_time.isoformat()} "
                f"{window.timezone} buffer time "
                f"(now {local_now.strftime('%Y-%m-%d %H:%M %Z')})"
            )

    return blockers


def market_sync_blockers_for_active_securities(
    engine=None,
    now_utc: datetime | None = None,
) -> list[str]:
    return market_sync_blockers(
        active_security_exchanges(engine),
        now_utc=now_utc,
    )
