from datetime import date

import pandas as pd
from sqlalchemy import text

from app.database.connection import get_engine


HEALTH_COLUMNS = [
    "ticker",
    "asset_name",
    "price_symbol",
    "exchange",
    "quote_currency",
    "latest_price_date",
    "latest_price_age_days",
    "latest_close_price",
    "latest_currency",
    "latest_fx_rate_to_eur",
    "latest_close_price_eur",
    "latest_source",
    "latest_daily_price_date",
    "latest_daily_age_days",
    "daily_close_price",
    "daily_currency",
    "daily_fx_rate_to_eur",
    "daily_close_price_eur",
    "latest_daily_source",
    "latest_broker_valuation_date",
    "latest_broker_market_value_eur",
    "missing_latest_price",
    "missing_daily_price",
    "stale_latest_price",
    "stale_daily_price",
    "invalid_latest_price",
    "invalid_daily_price",
    "currency_mismatch",
    "status",
    "issues",
]


def _coerce_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.date


def _coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def annotate_market_data_health(
    df: pd.DataFrame,
    today: date | None = None,
    stale_days: int = 5,
) -> pd.DataFrame:
    if today is None:
        today = date.today()

    if df.empty:
        return pd.DataFrame(columns=HEALTH_COLUMNS)

    result = df.copy()

    for column in ("latest_price_date", "latest_daily_price_date"):
        if column in result.columns:
            result[column] = _coerce_date(result[column])

    numeric_columns = [
        "latest_close_price",
        "latest_fx_rate_to_eur",
        "latest_close_price_eur",
        "daily_close_price",
        "daily_fx_rate_to_eur",
        "daily_close_price_eur",
    ]
    for column in numeric_columns:
        if column in result.columns:
            result[column] = _coerce_numeric(result[column])

    result["latest_price_age_days"] = result["latest_price_date"].apply(
        lambda value: (today - value).days if pd.notna(value) else pd.NA
    )
    result["latest_daily_age_days"] = result["latest_daily_price_date"].apply(
        lambda value: (today - value).days if pd.notna(value) else pd.NA
    )

    result["missing_latest_price"] = result["latest_price_date"].isna()
    result["missing_daily_price"] = result["latest_daily_price_date"].isna()

    result["stale_latest_price"] = (
        ~result["missing_latest_price"]
        & result["latest_price_age_days"].ge(stale_days + 1).fillna(False)
    )
    result["stale_daily_price"] = (
        ~result["missing_daily_price"]
        & result["latest_daily_age_days"].ge(stale_days + 1).fillna(False)
    )

    result["invalid_latest_price"] = (
        ~result["missing_latest_price"]
        & (
            result["latest_close_price"].isna()
            | result["latest_fx_rate_to_eur"].isna()
            | result["latest_close_price"].le(0).fillna(False)
            | result["latest_fx_rate_to_eur"].le(0).fillna(False)
        )
    )
    result["invalid_daily_price"] = (
        ~result["missing_daily_price"]
        & (
            result["daily_close_price"].isna()
            | result["daily_fx_rate_to_eur"].isna()
            | result["daily_close_price_eur"].isna()
            | result["daily_close_price"].le(0).fillna(False)
            | result["daily_fx_rate_to_eur"].le(0).fillna(False)
            | result["daily_close_price_eur"].le(0).fillna(False)
        )
    )

    latest_currency = result["latest_currency"].fillna("")
    daily_currency = result["daily_currency"].fillna("")
    quote_currency = result["quote_currency"].fillna("")
    result["currency_mismatch"] = (
        (~result["missing_latest_price"] & latest_currency.ne(quote_currency))
        | (~result["missing_daily_price"] & daily_currency.ne(quote_currency))
    )

    def issue_labels(row: pd.Series) -> list[str]:
        labels = []
        for column, label in (
            ("missing_latest_price", "missing latest"),
            ("missing_daily_price", "missing daily"),
            ("invalid_latest_price", "invalid latest"),
            ("invalid_daily_price", "invalid daily"),
            ("stale_latest_price", "stale latest"),
            ("stale_daily_price", "stale daily"),
            ("currency_mismatch", "currency mismatch"),
        ):
            if bool(row[column]):
                labels.append(label)
        return labels

    issues = result.apply(issue_labels, axis=1)
    result["issues"] = issues.apply(lambda labels: ", ".join(labels))
    result["status"] = issues.apply(
        lambda labels: "OK"
        if not labels
        else "MISSING"
        if any(label.startswith("missing") for label in labels)
        else "INVALID"
        if any(label.startswith("invalid") for label in labels)
        else "STALE"
        if any(label.startswith("stale") for label in labels)
        else "CHECK"
    )

    for column in HEALTH_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA

    return result[HEALTH_COLUMNS].sort_values("ticker").reset_index(drop=True)


def load_market_data_health(engine=None, stale_days: int = 5) -> pd.DataFrame:
    if engine is None:
        engine = get_engine()

    query = text("""
        WITH latest_prices AS (
            SELECT DISTINCT ON (ticker)
                ticker,
                price_date AS latest_price_date,
                NULLIF(close_price::TEXT, 'NaN')::NUMERIC AS latest_close_price,
                currency AS latest_currency,
                NULLIF(fx_rate_to_eur::TEXT, 'NaN')::NUMERIC AS latest_fx_rate_to_eur,
                NULLIF((close_price * fx_rate_to_eur)::TEXT, 'NaN')::NUMERIC
                    AS latest_close_price_eur,
                source AS latest_source
            FROM prices
            ORDER BY ticker, price_date DESC NULLS LAST, price_id DESC NULLS LAST
        ),
        latest_daily AS (
            SELECT DISTINCT ON (ticker)
                ticker,
                price_date AS latest_daily_price_date,
                NULLIF(close_price::TEXT, 'NaN')::NUMERIC AS daily_close_price,
                currency AS daily_currency,
                NULLIF(fx_rate_to_eur::TEXT, 'NaN')::NUMERIC AS daily_fx_rate_to_eur,
                NULLIF(close_price_eur::TEXT, 'NaN')::NUMERIC AS daily_close_price_eur,
                source AS latest_daily_source
            FROM daily_prices
            ORDER BY ticker, price_date DESC NULLS LAST, id DESC NULLS LAST
        ),
        latest_broker_valuations AS (
            SELECT DISTINCT ON (bpv.broker_name, bpv.ticker)
                bpv.broker_name,
                bpv.ticker,
                bpv.valuation_date AS latest_broker_valuation_date,
                NULLIF(bpv.market_value_eur::TEXT, 'NaN')::NUMERIC
                    AS latest_broker_market_value_eur
            FROM broker_position_valuations bpv
            JOIN v_positions p
              ON p.broker_name = bpv.broker_name
             AND p.ticker = bpv.ticker
            WHERE p.quantity > 0
            ORDER BY bpv.broker_name, bpv.ticker, bpv.valuation_date DESC, bpv.valuation_id DESC
        )
        SELECT
            s.ticker,
            s.asset_name,
            s.price_symbol,
            s.exchange,
            s.quote_currency,
            lp.latest_price_date,
            lp.latest_close_price,
            lp.latest_currency,
            lp.latest_fx_rate_to_eur,
            lp.latest_close_price_eur,
            lp.latest_source,
            ld.latest_daily_price_date,
            ld.daily_close_price,
            ld.daily_currency,
            ld.daily_fx_rate_to_eur,
            ld.daily_close_price_eur,
            ld.latest_daily_source,
            lbv.latest_broker_valuation_date,
            lbv.latest_broker_market_value_eur
        FROM securities s
        LEFT JOIN latest_prices lp
          ON lp.ticker = s.ticker
        LEFT JOIN latest_daily ld
          ON ld.ticker = s.ticker
        LEFT JOIN latest_broker_valuations lbv
          ON lbv.ticker = s.ticker
        WHERE s.active = TRUE
        ORDER BY s.ticker
    """)

    df = pd.read_sql(query, engine)
    return annotate_market_data_health(df, stale_days=stale_days)


def market_data_health_summary(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "active_securities": 0,
            "ok": 0,
            "stale": 0,
            "missing": 0,
            "invalid": 0,
            "check": 0,
        }

    status_counts = df["status"].value_counts()
    return {
        "active_securities": len(df),
        "ok": int(status_counts.get("OK", 0)),
        "stale": int(status_counts.get("STALE", 0)),
        "missing": int(status_counts.get("MISSING", 0)),
        "invalid": int(status_counts.get("INVALID", 0)),
        "check": int(status_counts.get("CHECK", 0)),
    }


def main():
    df = load_market_data_health()
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
