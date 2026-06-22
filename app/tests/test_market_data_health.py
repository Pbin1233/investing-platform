from datetime import date

import pandas as pd

from app.market_data.health import (
    annotate_market_data_health,
    market_data_health_summary,
)


def _base_row(**overrides):
    row = {
        "ticker": "SPY",
        "asset_name": "SPDR S&P 500 ETF",
        "price_symbol": "SPY",
        "exchange": "NYSE",
        "quote_currency": "USD",
        "latest_price_date": date(2026, 6, 10),
        "latest_close_price": 620.0,
        "latest_currency": "USD",
        "latest_fx_rate_to_eur": 0.86,
        "latest_close_price_eur": 533.2,
        "latest_source": "yfinance",
        "latest_daily_price_date": date(2026, 6, 10),
        "daily_close_price": 620.0,
        "daily_currency": "USD",
        "daily_fx_rate_to_eur": 0.86,
        "daily_close_price_eur": 533.2,
        "latest_daily_source": "yfinance",
    }
    row.update(overrides)
    return row


def test_market_data_health_marks_ok_rows():
    df = pd.DataFrame([_base_row()])

    result = annotate_market_data_health(
        df,
        today=date(2026, 6, 11),
        stale_days=5,
    )

    assert result.iloc[0]["status"] == "OK"
    assert result.iloc[0]["issues"] == ""
    assert result.iloc[0]["latest_price_age_days"] == 1
    assert result.iloc[0]["latest_daily_age_days"] == 1


def test_market_data_health_marks_missing_without_invalid_noise():
    df = pd.DataFrame([
        _base_row(
            latest_price_date=None,
            latest_close_price=None,
            latest_currency=None,
            latest_fx_rate_to_eur=None,
            latest_close_price_eur=None,
        )
    ])

    result = annotate_market_data_health(
        df,
        today=date(2026, 6, 11),
        stale_days=5,
    )
    row = result.iloc[0]

    assert row["status"] == "MISSING"
    assert bool(row["missing_latest_price"]) is True
    assert bool(row["invalid_latest_price"]) is False
    assert row["issues"] == "missing latest"


def test_market_data_health_accepts_broker_statement_valuation_without_quotes():
    df = pd.DataFrame([
        _base_row(
            ticker="IT0005532715",
            latest_price_date=None,
            latest_close_price=None,
            latest_currency=None,
            latest_fx_rate_to_eur=None,
            latest_close_price_eur=None,
            latest_daily_price_date=None,
            daily_close_price=None,
            daily_currency=None,
            daily_fx_rate_to_eur=None,
            daily_close_price_eur=None,
            latest_broker_valuation_date=date(2026, 3, 31),
            latest_broker_market_value_eur=25696.76,
        )
    ])

    result = annotate_market_data_health(
        df,
        today=date(2026, 6, 22),
        stale_days=5,
    )
    row = result.iloc[0]

    assert row["status"] == "OK"
    assert row["issues"] == ""
    assert bool(row["missing_latest_price"]) is False
    assert bool(row["missing_daily_price"]) is False


def test_market_data_health_marks_stale_daily_and_latest_prices():
    df = pd.DataFrame([
        _base_row(
            latest_price_date=date(2026, 6, 4),
            latest_daily_price_date=date(2026, 6, 3),
        )
    ])

    result = annotate_market_data_health(
        df,
        today=date(2026, 6, 11),
        stale_days=5,
    )
    row = result.iloc[0]

    assert row["status"] == "STALE"
    assert bool(row["stale_latest_price"]) is True
    assert bool(row["stale_daily_price"]) is True
    assert row["issues"] == "stale latest, stale daily"


def test_market_data_health_marks_invalid_nan_and_currency_mismatch():
    df = pd.DataFrame([
        _base_row(
            latest_close_price="NaN",
            daily_close_price_eur=-1,
            daily_currency="EUR",
        )
    ])

    result = annotate_market_data_health(
        df,
        today=date(2026, 6, 11),
        stale_days=5,
    )
    row = result.iloc[0]

    assert row["status"] == "INVALID"
    assert bool(row["invalid_latest_price"]) is True
    assert bool(row["invalid_daily_price"]) is True
    assert bool(row["currency_mismatch"]) is True
    assert row["issues"] == "invalid latest, invalid daily, currency mismatch"


def test_market_data_health_summary_counts_statuses():
    df = pd.DataFrame(
        [
            _base_row(ticker="OK"),
            _base_row(ticker="STALE", latest_price_date=date(2026, 6, 1)),
            _base_row(ticker="MISSING", latest_daily_price_date=None),
            _base_row(ticker="INVALID", latest_close_price=0),
        ]
    )

    result = annotate_market_data_health(
        df,
        today=date(2026, 6, 11),
        stale_days=5,
    )

    assert market_data_health_summary(result) == {
        "active_securities": 4,
        "ok": 1,
        "stale": 1,
        "missing": 1,
        "invalid": 1,
        "check": 0,
    }
