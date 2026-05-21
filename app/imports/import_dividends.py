import sys
import pandas as pd
from sqlalchemy import text

from app.database.connection import get_engine

CSV_PATH = "/data/imports/dividends.csv"

REQUIRED_COLUMNS = [
    "payment_date",
    "broker_name",
    "ticker",
    "gross_amount",
    "withholding_tax",
    "net_amount",
    "currency",
    "fx_rate_to_eur",
    "notes",
]


def main():

    if not os.path.exists(CSV_PATH):
        print(f"Missing file: {CSV_PATH}")
        sys.exit(1)

    df = pd.read_csv(CSV_PATH)

    missing = [
        col for col in REQUIRED_COLUMNS
        if col not in df.columns
    ]

    if missing:
        print(f"Missing columns: {missing}")
        sys.exit(1)

    df = df[REQUIRED_COLUMNS].copy()

    df["payment_date"] = pd.to_datetime(
        df["payment_date"]
    ).dt.date

    df["broker_name"] = (
        df["broker_name"]
        .astype(str)
        .str.strip()
    )

    df["ticker"] = (
        df["ticker"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df["currency"] = (
        df["currency"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df["notes"] = (
        df["notes"]
        .fillna("")
        .astype(str)
    )

    numeric_cols = [
        "gross_amount",
        "withholding_tax",
        "net_amount",
        "fx_rate_to_eur",
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(
            df[col],
            errors="raise"
        )

    engine = get_engine()

    with engine.begin() as conn:

        for broker in sorted(df["broker_name"].unique()):

            conn.execute(
                text("""
                    INSERT INTO brokers (
                        broker_name,
                        base_currency
                    )
                    VALUES (
                        :broker_name,
                        'EUR'
                    )
                    ON CONFLICT (
                        broker_name
                    )
                    DO NOTHING
                """),
                {
                    "broker_name": broker
                },
            )

        conn.execute(
            text("DELETE FROM dividends")
        )

        for row in df.itertuples(index=False):

            conn.execute(
                text("""
                    INSERT INTO dividends (
                        payment_date,
                        broker_name,
                        ticker,
                        gross_amount,
                        withholding_tax,
                        net_amount,
                        currency,
                        fx_rate_to_eur,
                        notes
                    )
                    VALUES (
                        :payment_date,
                        :broker_name,
                        :ticker,
                        :gross_amount,
                        :withholding_tax,
                        :net_amount,
                        :currency,
                        :fx_rate_to_eur,
                        :notes
                    )
                """),
                {
                    "payment_date": row.payment_date,
                    "broker_name": row.broker_name,
                    "ticker": row.ticker,
                    "gross_amount": row.gross_amount,
                    "withholding_tax": row.withholding_tax,
                    "net_amount": row.net_amount,
                    "currency": row.currency,
                    "fx_rate_to_eur": row.fx_rate_to_eur,
                    "notes": row.notes,
                },
            )

    print(f"Imported {len(df)} dividends.")
    print("Dividends table was replaced from CSV.")


if __name__ == "__main__":
    main()
