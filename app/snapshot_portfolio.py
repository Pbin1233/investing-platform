from datetime import date

from sqlalchemy import create_engine, text

from portfolio_value import calculate_portfolio
import os


DB_USER = os.getenv("POSTGRES_USER", "investing")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "change_this_password")
DB_NAME = os.getenv("POSTGRES_DB", "investing")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@postgres:5432/{DB_NAME}"


def get_engine():
    return create_engine(DATABASE_URL)


def snapshot_portfolio(snapshot_date=None):
    if snapshot_date is None:
        snapshot_date = date.today()

    engine = get_engine()

    portfolio = calculate_portfolio()

    if portfolio.empty:
        print("No portfolio data to snapshot.")
        return

    with engine.begin() as conn:

        conn.execute(
            text("""
                DELETE FROM portfolio_snapshots
                WHERE snapshot_date = :snapshot_date
            """),
            {"snapshot_date": snapshot_date},
        )

        for row in portfolio.itertuples(index=False):

            conn.execute(
                text("""
                    INSERT INTO portfolio_snapshots (
                        snapshot_date,
                        broker_name,
                        ticker,
                        quantity,
                        market_value_eur,
                        invested_eur,
                        unrealized_pl_eur,
                        unrealized_pl_pct
                    )
                    VALUES (
                        :snapshot_date,
                        :broker_name,
                        :ticker,
                        :quantity,
                        :market_value_eur,
                        :invested_eur,
                        :unrealized_pl_eur,
                        :unrealized_pl_pct
                    )
                """),
                {
                    "snapshot_date": snapshot_date,
                    "broker_name": row.broker_name,
                    "ticker": row.ticker,
                    "quantity": row.quantity,
                    "market_value_eur": row.market_value_eur,
                    "invested_eur": row.invested_eur,
                    "unrealized_pl_eur": row.unrealized_pl_eur,
                    "unrealized_pl_pct": row.unrealized_pl_pct,
                },
            )

    print(f"Snapshot saved for {snapshot_date}")


if __name__ == "__main__":
    snapshot_portfolio()
