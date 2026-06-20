import os
import pandas as pd
from sqlalchemy import text

from app.database.connection import get_engine


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

        latest_broker_valuations AS (
            SELECT DISTINCT ON (broker_name, ticker)
                broker_name,
                ticker,
                valuation_date,
                market_value_eur,
                currency
            FROM broker_position_valuations
            ORDER BY broker_name, ticker, valuation_date DESC, valuation_id DESC
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
            lbv.valuation_date AS broker_valuation_date,

            COALESCE(
                p.quantity * lp.close_price,
                lbv.market_value_eur
            ) AS market_value_native,
            COALESCE(
                p.quantity * lp.close_price * lp.fx_rate_to_eur,
                lbv.market_value_eur
            ) AS market_value_eur,

            i.invested_eur,

            COALESCE(
                p.quantity * lp.close_price * lp.fx_rate_to_eur,
                lbv.market_value_eur
            ) - i.invested_eur AS unrealized_pl_eur,

            CASE
                WHEN i.invested_eur <> 0
                THEN (
                    (
                        COALESCE(
                            p.quantity * lp.close_price * lp.fx_rate_to_eur,
                            lbv.market_value_eur
                        ) - i.invested_eur
                    ) / i.invested_eur
                ) * 100
                ELSE NULL
            END AS unrealized_pl_pct,

            CASE
                WHEN lp.close_price IS NOT NULL THEN 'market_price'
                WHEN lbv.market_value_eur IS NOT NULL THEN 'broker_statement'
                ELSE 'missing'
            END AS valuation_source

        FROM v_positions p

        LEFT JOIN latest_prices lp
            ON p.ticker = lp.ticker

        LEFT JOIN latest_broker_valuations lbv
            ON p.broker_name = lbv.broker_name
           AND p.ticker = lbv.ticker

        LEFT JOIN invested i
            ON p.broker_name = i.broker_name
           AND p.ticker = i.ticker

        ORDER BY market_value_eur DESC NULLS LAST
    """)

    return pd.read_sql(query, engine)


if __name__ == "__main__":
    df = calculate_portfolio()
    print(df.to_string(index=False))
