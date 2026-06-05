from datetime import date

import pandas as pd

from app.market_data import update_daily_prices


def test_merge_fx_rates_uses_latest_available_prior_rate():
    prices = pd.DataFrame(
        {
            "price_date": [date(2024, 12, 30), date(2024, 12, 31)],
            "Close": [100.0, 101.0],
        }
    )
    fx_rates = pd.DataFrame(
        {
            "price_date": [date(2024, 12, 30)],
            "fx_rate_to_eur": [0.92],
        }
    )

    merged = update_daily_prices._merge_fx_rates(prices, fx_rates)

    assert merged["fx_rate_to_eur"].tolist() == [0.92, 0.92]


def test_fetch_fx_history_to_eur_for_usd_uses_historical_eurusd(monkeypatch):
    def fake_fetch_price_history(price_symbol, start_date, end_date):
        assert price_symbol == "EURUSD=X"
        return pd.DataFrame(
            {
                "price_date": [date(2024, 12, 31)],
                "Close": [1.25],
                "Volume": [0],
            }
        )

    monkeypatch.setattr(
        update_daily_prices,
        "fetch_price_history",
        fake_fetch_price_history,
    )

    fx = update_daily_prices.fetch_fx_history_to_eur(
        "USD",
        date(2024, 12, 31),
        date(2024, 12, 31),
    )

    assert fx.iloc[0]["fx_rate_to_eur"] == 0.8
