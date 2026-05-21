from datetime import date

from sqlalchemy import text

from app.portfolio.portfolio_value import calculate_portfolio
from app.database.connection import get_engine
from app.ops.job_runs import start_job, finish_job


def snapshot_portfolio(snapshot_date=None):
    job_id = start_job("snapshot_portfolio")
    rows_processed = 0

    if snapshot_date is None:
        snapshot_date = date.today()

    try:
        engine = get_engine()

        portfolio = calculate_portfolio()

        if portfolio.empty:
            message = f"No portfolio data to snapshot for {snapshot_date}"
            print(message)
            finish_job(job_id, "success", rows_processed=0, message=message)
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

                rows_processed += 1

        message = f"Snapshot saved for {snapshot_date}"
        print(message)
        finish_job(
            job_id,
            "success",
            rows_processed=rows_processed,
            message=message,
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
    snapshot_portfolio()
