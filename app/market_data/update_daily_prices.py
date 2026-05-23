from datetime import date, timedelta

import pandas as pd
import yfinance as yf
from sqlalchemy import text

from app.database.connection import get_engine
from app.market_data.update_prices import fx_to_eur


def fetch_securities(engine):
    return pd.read_sql(
        text("""
            SELECT ticker, price_symbol, quote_currency
            FROM securities
            ORDER BY ticker
        """),
        engine,
    )


def fetch_price_history(price_symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
    hist = yf.Ticker(price_symbol).history(
        start=start_date.isoformat(),
        end=(end_date + timedelta(days=1)).isoformat(),
        auto_adjust=False,
    )

    if hist.empty:
        return pd.DataFrame()

    hist = hist.reset_index()
    hist["price_date"] = pd.to_datetime(hist["Date"]).dt.date

    return hist[["price_date", "Close", "Volume"]]


def upsert_daily_price(
    engine,
    ticker: str,
    price_symbol: str,
    price_date: date,
    close_price: float,
    currency: str,
    fx_rate_to_eur: float,
    volume: int | None,
):
    close_price_eur = close_price * fx_rate_to_eur

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO daily_prices (
                    ticker,
                    price_symbol,
                    price_date,
                    close_price,
                    currency,
                    fx_rate_to_eur,
                    close_price_eur,
                    volume,
                    source
                )
                VALUES (
                    :ticker,
                    :price_symbol,
                    :price_date,
                    :close_price,
                    :currency,
                    :fx_rate_to_eur,
                    :close_price_eur,
                    :volume,
                    'yfinance'
                )
                ON CONFLICT (ticker, price_date, source)
                DO UPDATE SET
                    price_symbol = EXCLUDED.price_symbol,
                    close_price = EXCLUDED.close_price,
                    currency = EXCLUDED.currency,
                    fx_rate_to_eur = EXCLUDED.fx_rate_to_eur,
                    close_price_eur = EXCLUDED.close_price_eur,
                    volume = EXCLUDED.volume
            """),
            {
                "ticker": ticker,
                "price_symbol": price_symbol,
                "price_date": price_date,
                "close_price": close_price,
                "currency": currency,
                "fx_rate_to_eur": fx_rate_to_eur,
                "close_price_eur": close_price_eur,
                "volume": volume,
            },
        )


def update_daily_prices(start_date: date | None = None, end_date: date | None = None) -> int:
    engine = get_engine()

    if end_date is None:
        end_date = date.today()

    if start_date is None:
        start_date = end_date - timedelta(days=10)

    securities = fetch_securities(engine)
    rows_processed = 0

    for security in securities.itertuples(index=False):
        hist = fetch_price_history(
            security.price_symbol,
            start_date=start_date,
            end_date=end_date,
        )

        if hist.empty:
            print(f"No historical prices for {security.ticker}")
            continue

        fx_rate = fx_to_eur(security.quote_currency)

        for row in hist.itertuples(index=False):
            upsert_daily_price(
                engine=engine,
                ticker=security.ticker,
                price_symbol=security.price_symbol,
                price_date=row.price_date,
                close_price=float(row.Close),
                currency=security.quote_currency,
                fx_rate_to_eur=fx_rate,
                volume=None if pd.isna(row.Volume) else int(row.Volume),
            )
            rows_processed += 1

        print(f"{security.ticker}: stored {len(hist)} daily prices")

    return rows_processed


def main():
    rows = update_daily_prices()
    print(f"Daily prices updated. Rows processed: {rows}")


if __name__ == "__main__":
    main()
