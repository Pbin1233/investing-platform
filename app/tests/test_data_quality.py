from datetime import date

import pandas as pd

from app.ops import data_quality


def test_stale_price_check_allows_broker_statement_valuations(monkeypatch):
    health = pd.DataFrame(
        [
            {
                "ticker": "IT0005532715",
                "exchange": "MOT",
                "quote_currency": "EUR",
                "latest_price_date": None,
                "latest_price_age_days": pd.NA,
                "latest_daily_price_date": None,
                "latest_daily_age_days": pd.NA,
                "latest_broker_valuation_date": date(2026, 3, 31),
                "missing_latest_price": True,
                "missing_daily_price": True,
                "stale_latest_price": False,
                "stale_daily_price": False,
                "invalid_latest_price": False,
                "invalid_daily_price": False,
                "currency_mismatch": False,
                "status": "MISSING",
                "issues": "missing latest, missing daily",
            }
        ]
    )

    monkeypatch.setattr(data_quality, "load_market_data_health", lambda stale_days: health)

    assert data_quality.check_stale_prices().empty
