import os
import pandas as pd
from sqlalchemy import create_engine, text

DB_USER = os.getenv("POSTGRES_USER", "investing")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "change_this_password")
DB_NAME = os.getenv("POSTGRES_DB", "investing")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@postgres:5432/{DB_NAME}"


def get_engine():
    return create_engine(DATABASE_URL)


def calculate_broker_cash():
    engine = get_engine()

    query = text("""
        WITH cash_flow_totals AS (
            SELECT
                broker_name,
                SUM(
                    CASE
                        WHEN flow_type = 'DEPOSIT'
                            THEN amount * fx_rate_to_eur
                        WHEN flow_type = 'WITHDRAWAL'
                            THEN -amount * fx_rate_to_eur
                        WHEN flow_type = 'INTEREST'
                            THEN amount * fx_rate_to_eur
                        WHEN flow_type = 'FEE'
                            THEN -amount * fx_rate_to_eur
                        WHEN flow_type = 'TAX'
                            THEN -amount * fx_rate_to_eur
                        ELSE 0
                    END
                ) AS cash_from_flows_eur
            FROM cash_flows
            GROUP BY broker_name
        ),

        trade_totals AS (
            SELECT
                broker_name,
                SUM(
                    CASE
                        WHEN action = 'BUY'
                            THEN -(quantity * price + fees) * fx_rate_to_eur
                        WHEN action = 'SELL'
                            THEN (quantity * price - fees) * fx_rate_to_eur
                        ELSE 0
                    END
                ) AS cash_from_trades_eur
            FROM transactions
            GROUP BY broker_name
        ),

        dividend_totals AS (
            SELECT
                broker_name,
                SUM(net_amount * fx_rate_to_eur) AS cash_from_dividends_eur
            FROM dividends
            GROUP BY broker_name
        ),

        brokers_all AS (
            SELECT broker_name FROM brokers
            UNION
            SELECT broker_name FROM cash_flows
            UNION
            SELECT broker_name FROM transactions
            UNION
            SELECT broker_name FROM dividends
        )

        SELECT
            b.broker_name,
            COALESCE(cf.cash_from_flows_eur, 0) AS cash_from_flows_eur,
            COALESCE(tt.cash_from_trades_eur, 0) AS cash_from_trades_eur,
            COALESCE(dt.cash_from_dividends_eur, 0) AS cash_from_dividends_eur,
            COALESCE(cf.cash_from_flows_eur, 0)
            + COALESCE(tt.cash_from_trades_eur, 0)
            + COALESCE(dt.cash_from_dividends_eur, 0)
                AS cash_balance_eur
        FROM brokers_all b
        LEFT JOIN cash_flow_totals cf
            ON b.broker_name = cf.broker_name
        LEFT JOIN trade_totals tt
            ON b.broker_name = tt.broker_name
        LEFT JOIN dividend_totals dt
            ON b.broker_name = dt.broker_name
        ORDER BY b.broker_name
    """)

    return pd.read_sql(query, engine)


if __name__ == "__main__":
    df = calculate_broker_cash()
    print(df.to_string(index=False))
