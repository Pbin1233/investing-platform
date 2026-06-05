from datetime import date, timedelta

import pandas as pd
import yfinance as yf
from sqlalchemy import text

from app.database.connection import get_engine


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


def _merge_fx_rates(prices: pd.DataFrame, fx_rates: pd.DataFrame) -> pd.DataFrame:
    prices = prices.copy()
    prices["price_date"] = pd.to_datetime(prices["price_date"])

    fx_rates = fx_rates.copy()
    fx_rates["price_date"] = pd.to_datetime(fx_rates["price_date"])
    fx_rates = fx_rates.sort_values("price_date")

    merged = pd.merge_asof(
        prices.sort_values("price_date"),
        fx_rates[["price_date", "fx_rate_to_eur"]],
        on="price_date",
        direction="backward",
    )
    merged["price_date"] = merged["price_date"].dt.date

    return merged


def fetch_fx_history_to_eur(
    currency: str,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    currency = currency.upper()

    if currency == "EUR":
        dates = pd.date_range(start=start_date, end=end_date)
        return pd.DataFrame(
            {
                "price_date": dates.date,
                "fx_rate_to_eur": 1.0,
            }
        )

    eurusd = fetch_price_history("EURUSD=X", start_date, end_date)
    if eurusd.empty:
        raise RuntimeError("Could not fetch historical EUR/USD rates")

    eurusd = eurusd.rename(columns={"Close": "eur_usd"})

    if currency == "USD":
        fx = eurusd[["price_date", "eur_usd"]].copy()
        fx["fx_rate_to_eur"] = 1 / fx["eur_usd"]
        return fx[["price_date", "fx_rate_to_eur"]]

    if currency == "KRW":
        usdkrw = fetch_price_history("USDKRW=X", start_date, end_date)
        if usdkrw.empty:
            raise RuntimeError("Could not fetch historical USD/KRW rates")

        usdkrw = usdkrw.rename(columns={"Close": "krw_per_usd"})
        usdkrw["price_date"] = pd.to_datetime(usdkrw["price_date"])
        eurusd["price_date"] = pd.to_datetime(eurusd["price_date"])
        fx = pd.merge_asof(
            usdkrw[["price_date", "krw_per_usd"]].sort_values("price_date"),
            eurusd[["price_date", "eur_usd"]].sort_values("price_date"),
            on="price_date",
            direction="backward",
        )
        fx["price_date"] = fx["price_date"].dt.date
        fx["fx_rate_to_eur"] = 1 / (fx["krw_per_usd"] * fx["eur_usd"])
        return fx[["price_date", "fx_rate_to_eur"]]

    raise RuntimeError(f"Unsupported quote currency: {currency}")


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
    fx_history_cache: dict[str, pd.DataFrame] = {}

    for security in securities.itertuples(index=False):
        hist = fetch_price_history(
            security.price_symbol,
            start_date=start_date,
            end_date=end_date,
        )

        if hist.empty:
            print(f"No historical prices for {security.ticker}")
            continue

        hist = hist.dropna(subset=["Close"])

        if hist.empty:
            print(f"No usable historical prices for {security.ticker}")
            continue

        currency = security.quote_currency.upper()
        if currency not in fx_history_cache:
            fx_history_cache[currency] = fetch_fx_history_to_eur(
                currency,
                start_date=start_date,
                end_date=end_date,
            )

        hist = _merge_fx_rates(hist, fx_history_cache[currency])
        hist = hist.dropna(subset=["fx_rate_to_eur"])

        for row in hist.itertuples(index=False):
            upsert_daily_price(
                engine=engine,
                ticker=security.ticker,
                price_symbol=security.price_symbol,
                price_date=row.price_date,
                close_price=float(row.Close),
                currency=security.quote_currency,
                fx_rate_to_eur=float(row.fx_rate_to_eur),
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
