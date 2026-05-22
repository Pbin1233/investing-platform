import pandas as pd
from sqlalchemy import text

from app.database.connection import get_engine
from app.portfolio.realized_gains import calculate_all_realized_gains


def calculate_yearly_summary() -> pd.DataFrame:
    engine = get_engine()

    cash_flows = pd.read_sql(
        text("""
            SELECT
                EXTRACT(YEAR FROM flow_date)::INT AS year,
                SUM(CASE WHEN flow_type = 'DEPOSIT'
                    THEN amount * fx_rate_to_eur ELSE 0 END) AS deposits_eur,
                SUM(CASE WHEN flow_type = 'WITHDRAWAL'
                    THEN amount * fx_rate_to_eur ELSE 0 END) AS withdrawals_eur
            FROM cash_flows
            GROUP BY year
        """),
        engine,
    )

    dividends = pd.read_sql(
        text("""
            SELECT
                EXTRACT(YEAR FROM payment_date)::INT AS year,
                SUM(gross_amount * fx_rate_to_eur) AS gross_dividends_eur,
                SUM(withholding_tax * fx_rate_to_eur) AS withholding_tax_eur,
                SUM(net_amount * fx_rate_to_eur) AS net_dividends_eur
            FROM dividends
            GROUP BY year
        """),
        engine,
    )

    snapshots = pd.read_sql(
        text("""
            WITH ranked AS (
                SELECT
                    EXTRACT(YEAR FROM snapshot_date)::INT AS year,
                    snapshot_date,
                    SUM(market_value_eur) AS year_end_market_value_eur,
                    ROW_NUMBER() OVER (
                        PARTITION BY EXTRACT(YEAR FROM snapshot_date)::INT
                        ORDER BY snapshot_date DESC
                    ) AS rn
                FROM portfolio_snapshots
                GROUP BY snapshot_date
            )
            SELECT year, snapshot_date AS year_end_snapshot_date, year_end_market_value_eur
            FROM ranked
            WHERE rn = 1
        """),
        engine,
    )

    gains = calculate_all_realized_gains()

    if gains.empty:
        realized = pd.DataFrame(columns=["year", "realized_gain_eur"])
    else:
        realized = gains.copy()
        realized["year"] = pd.to_datetime(realized["sell_date"]).dt.year
        realized = (
            realized
            .groupby("year", as_index=False)["realized_gain_eur"]
            .sum()
        )

    frames = [cash_flows, dividends, snapshots, realized]
    years = sorted(
        set().union(*[
            set(df["year"].dropna().astype(int))
            for df in frames
            if not df.empty and "year" in df.columns
        ])
    )

    summary = pd.DataFrame({"year": years})

    for df in frames:
        if not df.empty:
            summary = summary.merge(df, on="year", how="left")

    numeric_cols = [
        "deposits_eur",
        "withdrawals_eur",
        "gross_dividends_eur",
        "withholding_tax_eur",
        "net_dividends_eur",
        "year_end_market_value_eur",
        "realized_gain_eur",
    ]

    for col in numeric_cols:
        if col not in summary.columns:
            summary[col] = 0.0
        summary[col] = pd.to_numeric(summary[col], errors="coerce").fillna(0.0)

    summary["net_external_cash_flow_eur"] = (
        summary["deposits_eur"] - summary["withdrawals_eur"]
    )

    summary["estimated_capital_gains_tax_eur"] = (
        summary["realized_gain_eur"].clip(lower=0) * 0.26
    )

    return summary.sort_values("year")


def main():
    df = calculate_yearly_summary()
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
