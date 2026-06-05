import pandas as pd
from sqlalchemy import text

from app.database.connection import get_engine


def check_negative_positions() -> pd.DataFrame:
    engine = get_engine()

    return pd.read_sql(
        text("""
            SELECT
                broker_name,
                ticker,
                SUM(
                    CASE
                        WHEN action = 'BUY' THEN quantity
                        WHEN action = 'SELL' THEN -quantity
                        WHEN action = 'SPLIT' THEN quantity
                        ELSE 0
                    END
                ) AS quantity
            FROM transactions
            GROUP BY broker_name, ticker
            HAVING SUM(
                CASE
                    WHEN action = 'BUY' THEN quantity
                    WHEN action = 'SELL' THEN -quantity
                    WHEN action = 'SPLIT' THEN quantity
                    ELSE 0
                END
            ) < 0
            ORDER BY broker_name, ticker
        """),
        engine,
    )


def check_duplicate_transactions() -> pd.DataFrame:
    engine = get_engine()

    return pd.read_sql(
        text("""
            SELECT
                trade_date,
                broker_name,
                ticker,
                action,
                quantity,
                price,
                COUNT(*) AS duplicate_count
            FROM transactions
            GROUP BY
                trade_date,
                broker_name,
                ticker,
                action,
                quantity,
                price
            HAVING COUNT(*) > 1
            ORDER BY duplicate_count DESC
        """),
        engine,
    )


def check_missing_fx_rates() -> pd.DataFrame:
    engine = get_engine()

    return pd.read_sql(
        text("""
            SELECT *
            FROM transactions
            WHERE fx_rate_to_eur IS NULL
               OR fx_rate_to_eur <= 0
        """),
        engine,
    )


def check_stale_prices(days: int = 5) -> pd.DataFrame:
    engine = get_engine()

    return pd.read_sql(
        text(f"""
            SELECT
                ticker,
                MAX(price_date) AS latest_price_date
            FROM daily_prices
            GROUP BY ticker
            HAVING MAX(price_date) < CURRENT_DATE - INTERVAL '{days} days'
            ORDER BY latest_price_date
        """),
        engine,
    )


def run_all_checks() -> dict:
    checks = {
        "negative_positions": check_negative_positions(),
        "duplicate_transactions": check_duplicate_transactions(),
        "missing_fx_rates": check_missing_fx_rates(),
        "stale_prices": check_stale_prices(),
    }

    return checks


def main():
    checks = run_all_checks()

    for name, df in checks.items():
        print("=" * 80)
        print(name)

        if df.empty:
            print("OK")
        else:
            print(df.to_string(index=False))


if __name__ == "__main__":
    main()
