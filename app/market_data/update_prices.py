import os
from datetime import date

import pandas as pd
import yfinance as yf
from sqlalchemy import text

from app.database.connection import get_engine

def usd_to_eur_rate():
    eurusd = yf.Ticker("EURUSD=X").history(period="1d")
    if eurusd.empty:
        raise RuntimeError("Could not fetch EUR/USD rate")

    eur_usd = float(eurusd["Close"].iloc[-1])
    return 1 / eur_usd


def fx_to_eur(currency):
    currency = currency.upper()

    if currency == "EUR":
        return 1.0

    if currency == "USD":
        return usd_to_eur_rate()

    raise RuntimeError(f"Unsupported quote currency: {currency}")


def fetch_securities(engine):
    return pd.read_sql(
        text("""
            SELECT ticker, price_symbol, quote_currency
            FROM securities
            ORDER BY ticker
        """),
        engine,
    )


def fetch_price(price_symbol):
    ticker_obj = yf.Ticker(price_symbol)
    hist = ticker_obj.history(period="1d")

    if hist.empty:
        return None

    return float(hist["Close"].iloc[-1])


def upsert_price(engine, ticker, close_price, currency, fx_rate_to_eur):
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO prices
                (price_date, ticker, close_price, currency, fx_rate_to_eur, source)
                VALUES
                (:price_date, :ticker, :close_price, :currency, :fx_rate_to_eur, 'yfinance')
                ON CONFLICT (price_date, ticker, source)
                DO UPDATE SET
                    close_price = EXCLUDED.close_price,
                    currency = EXCLUDED.currency,
                    fx_rate_to_eur = EXCLUDED.fx_rate_to_eur
            """),
            {
                "price_date": date.today(),
                "ticker": ticker,
                "close_price": close_price,
                "currency": currency,
                "fx_rate_to_eur": fx_rate_to_eur,
            },
        )


def main():
    engine = get_engine()
    securities = fetch_securities(engine)

    for row in securities.itertuples(index=False):
        close_price = fetch_price(row.price_symbol)

        if close_price is None:
            print(f"No price for {row.ticker} using {row.price_symbol}")
            continue

        fx_rate = fx_to_eur(row.quote_currency)

        upsert_price(
            engine,
            row.ticker,
            close_price,
            row.quote_currency,
            fx_rate,
        )

        print(
            f"{row.ticker}: {close_price} {row.quote_currency}, "
            f"FX to EUR {fx_rate}"
        )


if __name__ == "__main__":
    main()
