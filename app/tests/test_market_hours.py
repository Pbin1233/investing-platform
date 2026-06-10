from datetime import datetime
from zoneinfo import ZoneInfo

from app.market_data.market_hours import market_sync_blockers


ACTIVE_EXCHANGES = ["Euronext Amsterdam", "NASDAQ", "KRX"]


def test_market_sync_blocks_when_us_market_is_open():
    now = datetime(2026, 6, 10, 15, 0, tzinfo=ZoneInfo("America/New_York"))

    blockers = market_sync_blockers(ACTIVE_EXCHANGES, now_utc=now)

    assert any(blocker.startswith("NASDAQ:") for blocker in blockers)


def test_market_sync_allows_rome_late_evening_window():
    now = datetime(2026, 6, 10, 23, 0, tzinfo=ZoneInfo("Europe/Rome"))

    blockers = market_sync_blockers(ACTIVE_EXCHANGES, now_utc=now)

    assert blockers == []


def test_market_sync_blocks_when_korea_market_is_open():
    now = datetime(2026, 6, 11, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))

    blockers = market_sync_blockers(ACTIVE_EXCHANGES, now_utc=now)

    assert any(blocker.startswith("KRX:") for blocker in blockers)
