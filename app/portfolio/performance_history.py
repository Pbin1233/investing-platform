import pandas as pd
from sqlalchemy import text

from app.database.connection import get_engine


def calculate_performance_history() -> pd.DataFrame:
    engine = get_engine()

    history = pd.read_sql(
        text("""
            SELECT
                snapshot_date,
                SUM(market_value_eur) AS total_value_eur
            FROM portfolio_snapshots
            GROUP BY snapshot_date
            ORDER BY snapshot_date
        """),
        engine,
    )

    if history.empty:
        return history

    history["snapshot_date"] = pd.to_datetime(history["snapshot_date"])
    history["total_value_eur"] = pd.to_numeric(
        history["total_value_eur"],
        errors="coerce",
    )

    history = history.dropna(subset=["total_value_eur"])
    history = history.sort_values("snapshot_date")

    history["daily_return_pct"] = (
        history["total_value_eur"].pct_change() * 100
    )

    history["running_peak_eur"] = history["total_value_eur"].cummax()

    history["drawdown_pct"] = (
        (history["total_value_eur"] - history["running_peak_eur"])
        / history["running_peak_eur"]
        * 100
    )

    return history


def main():
    df = calculate_performance_history()
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
