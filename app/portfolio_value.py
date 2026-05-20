import os
import pandas as pd
from sqlalchemy import create_engine, text


DB_USER = os.getenv("POSTGRES_USER", "investing")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "change_this_password")
DB_NAME = os.getenv("POSTGRES_DB", "investing")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@postgres:5432/{DB_NAME}"


def get_engine():
    return create_engine(DATABASE_URL)


def calculate_portfolio():
    engine = get_engine()

    query = text("""
        WITH latest_prices AS (
            SELECT DISTINCT ON (ticker)
                ticker,
                close_price,
                currency,
                fx_rate_to_eur,
                price_date
            FROM prices
            ORDER BY ticker, price_date DESC, price_id DESC
        ),

        invested AS (
            SELECT
                broker_name,
                ticker,
                SUM(
                    CASE
                        WHEN action = 'BUY'
                        THEN (quantity * price + fees) * fx_rate_to_eur
                        WHEN action = 'SELL'
                        THEN -((quantity * price - fees) * fx_rate_to_eur)
                        ELSE 0
                    END
                ) AS invested_eur
            FROM transactions
            GROUP BY broker_name, ticker
        )

        SELECT
            p.broker_name,
            p.ticker,
            p.quantity,

            lp.close_price,
            lp.currency,
            lp.fx_rate_to_eur,
            lp.price_date,

            p.quantity * lp.close_price AS market_value_native,
            p.quantity * lp.close_price * lp.fx_rate_to_eur AS market_value_eur,

            i.invested_eur,

            p.quantity * lp.close_price * lp.fx_rate_to_eur - i.invested_eur AS unrealized_pl_eur,

            CASE
                WHEN i.invested_eur <> 0
                THEN ((p.quantity * lp.close_price * lp.fx_rate_to_eur - i.invested_eur) / i.invested_eur) * 100
                ELSE NULL
            END AS unrealized_pl_pct

        FROM v_positions p

        LEFT JOIN latest_prices lp
            ON p.ticker = lp.ticker

        LEFT JOIN invested i
            ON p.broker_name = i.broker_name
           AND p.ticker = i.ticker

        ORDER BY market_value_eur DESC NULLS LAST
    """)

    return pd.read_sql(query, engine)


if __name__ == "__main__":
    df = calculate_portfolio()
    print(df.to_string(index=False))
