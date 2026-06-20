import pandas as pd
from sqlalchemy import text

from app.database.connection import get_engine
from app.market_data.health import load_market_data_health


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
    health = load_market_data_health(stale_days=days)

    if health.empty:
        return health

    has_broker_valuation = health["latest_broker_valuation_date"].notna()
    missing_or_stale_market_price = (
        health["missing_latest_price"]
        | health["missing_daily_price"]
        | health["stale_latest_price"]
        | health["stale_daily_price"]
    ) & ~has_broker_valuation

    return health[
        missing_or_stale_market_price
        | health["invalid_latest_price"]
        | health["invalid_daily_price"]
        | health["currency_mismatch"]
    ][
        [
            "ticker",
            "exchange",
            "quote_currency",
            "latest_price_date",
            "latest_price_age_days",
            "latest_daily_price_date",
            "latest_daily_age_days",
            "latest_broker_valuation_date",
            "status",
            "issues",
        ]
    ]


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
