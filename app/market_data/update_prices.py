from datetime import date

import pandas as pd
import yfinance as yf
from sqlalchemy import text

from app.database.connection import get_engine
from app.ops.job_runs import start_job, finish_job

def usd_to_eur_rate():
    eurusd = yf.Ticker("EURUSD=X").history(period="1d")
    if eurusd.empty:
        raise RuntimeError("Could not fetch EUR/USD rate")

    eur_usd = float(eurusd["Close"].iloc[-1])
    return 1 / eur_usd


def krw_to_eur_rate():
    usdk_rw = yf.Ticker("USDKRW=X").history(period="1d")
    eurusd = yf.Ticker("EURUSD=X").history(period="1d")

    if usdk_rw.empty:
        raise RuntimeError("Could not fetch USD/KRW rate")

    if eurusd.empty:
        raise RuntimeError("Could not fetch EUR/USD rate")

    krw_per_usd = float(usdk_rw["Close"].iloc[-1])
    usd_per_eur = float(eurusd["Close"].iloc[-1])
    return 1 / (krw_per_usd * usd_per_eur)


def fx_to_eur(currency):
    currency = currency.upper()

    if currency == "EUR":
        return 1.0

    if currency == "USD":
        return usd_to_eur_rate()

    if currency == "KRW":
        return krw_to_eur_rate()

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
    job_id = start_job("update_prices")
    rows_processed = 0

    try:
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

            rows_processed += 1

            print(
                f"{row.ticker}: {close_price} {row.quote_currency}, "
                f"FX to EUR {fx_rate}"
            )

        finish_job(
            job_id,
            "success",
            rows_processed=rows_processed,
            message="Market prices updated",
        )

    except Exception as exc:
        finish_job(
            job_id,
            "failed",
            rows_processed=rows_processed,
            message=str(exc),
        )
        raise


if __name__ == "__main__":
    main()
