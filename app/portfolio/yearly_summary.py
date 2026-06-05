import pandas as pd
from sqlalchemy import text

from app.database.connection import get_engine
from app.portfolio.realized_gains import calculate_all_realized_gains


CAPITAL_GAINS_TAX_RATE = 0.26
DIVIDEND_TAX_RATE = 0.26
IVAFE_TAX_RATE = 0.002


def _year_end_market_values(
    engine,
    years: list[int],
    by_broker: bool = False,
) -> pd.DataFrame:
    if not years:
        columns = ["year", "year_end_market_value_eur", "year_end_unpriced_positions"]
        if by_broker:
            columns.insert(1, "broker_name")
        return pd.DataFrame(columns=columns)

    values = ", ".join(f"({int(year)})" for year in sorted(set(years)))
    broker_cols = "p.broker_name," if by_broker else ""
    broker_group = ", p.broker_name" if by_broker else ""
    broker_order = ", p.broker_name" if by_broker else ""

    query = text(f"""
        WITH year_ends(year) AS (
            VALUES {values}
        ),

        positions AS (
            SELECT
                y.year,
                make_date(y.year, 12, 31) AS year_end_date,
                t.broker_name,
                t.ticker,
                SUM(
                    CASE
                        WHEN t.action = 'BUY' THEN t.quantity
                        WHEN t.action = 'SELL' THEN -t.quantity
                        WHEN t.action = 'SPLIT' THEN t.quantity
                    END
                ) AS quantity
            FROM year_ends y
            JOIN transactions t
              ON t.trade_date <= make_date(y.year, 12, 31)
            GROUP BY y.year, t.broker_name, t.ticker
            HAVING SUM(
                CASE
                    WHEN t.action = 'BUY' THEN t.quantity
                    WHEN t.action = 'SELL' THEN -t.quantity
                    WHEN t.action = 'SPLIT' THEN t.quantity
                END
            ) <> 0
        ),

        valued_positions AS (
            SELECT
                p.year,
                {broker_cols}
                p.ticker,
                p.quantity,
                latest_price.close_price_eur,
                p.quantity * latest_price.close_price_eur AS market_value_eur
            FROM positions p
            LEFT JOIN LATERAL (
                SELECT close_price_eur
                FROM (
                    SELECT
                        price_date,
                        close_price_eur,
                        id AS sort_id
                    FROM daily_prices
                    WHERE ticker = p.ticker
                      AND price_date <= p.year_end_date
                      AND close_price_eur::TEXT <> 'NaN'

                    UNION ALL

                    SELECT
                        price_date,
                        close_price * fx_rate_to_eur AS close_price_eur,
                        price_id AS sort_id
                    FROM prices
                    WHERE ticker = p.ticker
                      AND price_date <= p.year_end_date
                      AND (close_price * fx_rate_to_eur)::TEXT <> 'NaN'
                ) candidate_prices
                ORDER BY price_date DESC, sort_id DESC
                LIMIT 1
            ) latest_price ON TRUE
        )

        SELECT
            year,
            {broker_cols}
            COALESCE(SUM(market_value_eur), 0) AS year_end_market_value_eur,
            SUM(CASE WHEN close_price_eur IS NULL THEN 1 ELSE 0 END)::INT
                AS year_end_unpriced_positions
        FROM valued_positions p
        GROUP BY year{broker_group}
        ORDER BY year{broker_order}
    """)

    return pd.read_sql(query, engine)


def _add_tax_estimates(summary: pd.DataFrame) -> pd.DataFrame:
    summary = summary.copy()

    summary["taxable_realized_gain_eur"] = (
        summary["realized_gain_eur"].clip(lower=0)
    )
    summary["capital_gains_tax_eur"] = (
        summary["taxable_realized_gain_eur"] * CAPITAL_GAINS_TAX_RATE
    )
    summary["dividend_tax_eur"] = (
        summary["gross_dividends_eur"] * DIVIDEND_TAX_RATE
    )
    summary["dividend_withholding_credit_eur"] = summary[
        ["withholding_tax_eur", "dividend_tax_eur"]
    ].min(axis=1)
    summary["dividend_tax_due_after_withholding_eur"] = (
        summary["dividend_tax_eur"]
        - summary["dividend_withholding_credit_eur"]
    ).clip(lower=0)
    summary["ivafe_tax_eur"] = (
        summary["year_end_market_value_eur"] * IVAFE_TAX_RATE
    )
    summary["estimated_total_tax_liability_eur"] = (
        summary["capital_gains_tax_eur"]
        + summary["dividend_tax_eur"]
        + summary["ivafe_tax_eur"]
    )
    summary["estimated_tax_due_after_withholding_eur"] = (
        summary["capital_gains_tax_eur"]
        + summary["dividend_tax_due_after_withholding_eur"]
        + summary["ivafe_tax_eur"]
    )

    return summary


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

    frames = [cash_flows, dividends, realized]
    years = sorted(
        set().union(*[
            set(df["year"].dropna().astype(int))
            for df in frames
            if not df.empty and "year" in df.columns
        ])
    )

    summary = pd.DataFrame({"year": years})
    year_end_values = _year_end_market_values(engine, years)
    frames.append(year_end_values)

    for df in frames:
        if not df.empty:
            summary = summary.merge(df, on="year", how="left")

    numeric_cols = [
        "deposits_eur",
        "withdrawals_eur",
        "gross_dividends_eur",
        "withholding_tax_eur",
        "net_dividends_eur",
        "realized_gain_eur",
        "year_end_market_value_eur",
        "year_end_unpriced_positions",
    ]

    for col in numeric_cols:
        if col not in summary.columns:
            summary[col] = 0.0
        summary[col] = pd.to_numeric(summary[col], errors="coerce").fillna(0.0)

    summary["net_external_cash_flow_eur"] = (
        summary["deposits_eur"] - summary["withdrawals_eur"]
    )
    summary = _add_tax_estimates(summary)

    return summary.sort_values("year")

def calculate_yearly_summary_by_broker() -> pd.DataFrame:
    engine = get_engine()

    cash_flows = pd.read_sql(
        text("""
            SELECT
                EXTRACT(YEAR FROM flow_date)::INT AS year,
                broker_name,
                SUM(CASE WHEN flow_type = 'DEPOSIT' THEN amount * fx_rate_to_eur ELSE 0 END) AS deposits_eur,
                SUM(CASE WHEN flow_type = 'WITHDRAWAL' THEN amount * fx_rate_to_eur ELSE 0 END) AS withdrawals_eur
            FROM cash_flows
            GROUP BY year, broker_name
        """),
        engine,
    )

    dividends = pd.read_sql(
        text("""
            SELECT
                EXTRACT(YEAR FROM payment_date)::INT AS year,
                broker_name,
                SUM(gross_amount * fx_rate_to_eur) AS gross_dividends_eur,
                SUM(withholding_tax * fx_rate_to_eur) AS withholding_tax_eur,
                SUM(net_amount * fx_rate_to_eur) AS net_dividends_eur
            FROM dividends
            GROUP BY year, broker_name
        """),
        engine,
    )

    gains = calculate_all_realized_gains()

    if gains.empty:
        realized = pd.DataFrame(
            columns=["year", "broker_name", "realized_gain_eur"]
        )
    else:
        realized = gains.copy()
        realized["year"] = pd.to_datetime(realized["sell_date"]).dt.year
        realized = (
            realized
            .groupby(["year", "broker_name"], as_index=False)["realized_gain_eur"]
            .sum()
        )

    frames = [cash_flows, dividends, realized]

    keys = pd.concat(
        [
            df[["year", "broker_name"]]
            for df in frames
            if not df.empty and {"year", "broker_name"}.issubset(df.columns)
        ],
        ignore_index=True,
    ).drop_duplicates()

    if keys.empty:
        return pd.DataFrame()

    summary = keys.copy()
    year_end_values = _year_end_market_values(
        engine,
        sorted(keys["year"].dropna().astype(int).unique()),
        by_broker=True,
    )
    frames.append(year_end_values)

    for df in frames:
        if not df.empty:
            summary = summary.merge(df, on=["year", "broker_name"], how="left")

    numeric_cols = [
        "deposits_eur",
        "withdrawals_eur",
        "gross_dividends_eur",
        "withholding_tax_eur",
        "net_dividends_eur",
        "realized_gain_eur",
        "year_end_market_value_eur",
        "year_end_unpriced_positions",
    ]

    for col in numeric_cols:
        if col not in summary.columns:
            summary[col] = 0.0

        summary[col] = pd.to_numeric(summary[col], errors="coerce").fillna(0.0)

    summary["net_external_cash_flow_eur"] = (
        summary["deposits_eur"] - summary["withdrawals_eur"]
    )
    summary = _add_tax_estimates(summary)

    return summary.sort_values(["year", "broker_name"])

def main():
    df = calculate_yearly_summary()
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
