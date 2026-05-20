import os
import sys
import pandas as pd
from sqlalchemy import create_engine, text

DB_USER = os.getenv("POSTGRES_USER", "investing")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "change_this_password")
DB_NAME = os.getenv("POSTGRES_DB", "investing")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@postgres:5432/{DB_NAME}"
CSV_PATH = "/data/imports/cash_flows.csv"

REQUIRED_COLUMNS = [
    "flow_date",
    "broker_name",
    "flow_type",
    "amount",
    "currency",
    "fx_rate_to_eur",
    "notes",
]

VALID_TYPES = {"DEPOSIT", "WITHDRAWAL", "INTEREST", "FEE", "TAX"}


def main():
    if not os.path.exists(CSV_PATH):
        print(f"Missing file: {CSV_PATH}")
        sys.exit(1)

    df = pd.read_csv(CSV_PATH)

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        print(f"Missing columns: {missing}")
        sys.exit(1)

    df = df[REQUIRED_COLUMNS].copy()

    df["flow_date"] = pd.to_datetime(df["flow_date"]).dt.date
    df["broker_name"] = df["broker_name"].astype(str).str.strip()
    df["flow_type"] = df["flow_type"].astype(str).str.strip().str.upper()
    df["currency"] = df["currency"].astype(str).str.strip().str.upper()
    df["notes"] = df["notes"].fillna("").astype(str)

    for col in ["amount", "fx_rate_to_eur"]:
        df[col] = pd.to_numeric(df[col], errors="raise")

    invalid = sorted(set(df["flow_type"]) - VALID_TYPES)
    if invalid:
        print(f"Invalid flow_type values: {invalid}")
        sys.exit(1)

    engine = create_engine(DATABASE_URL)

    with engine.begin() as conn:
        for broker in sorted(df["broker_name"].unique()):
            conn.execute(
                text("""
                    INSERT INTO brokers (broker_name, base_currency)
                    VALUES (:broker_name, 'EUR')
                    ON CONFLICT (broker_name) DO NOTHING
                """),
                {"broker_name": broker},
            )

        conn.execute(text("DELETE FROM cash_flows"))

        for row in df.itertuples(index=False):
            conn.execute(
                text("""
                    INSERT INTO cash_flows (
                        flow_date,
                        broker_name,
                        flow_type,
                        amount,
                        currency,
                        fx_rate_to_eur,
                        notes
                    )
                    VALUES (
                        :flow_date,
                        :broker_name,
                        :flow_type,
                        :amount,
                        :currency,
                        :fx_rate_to_eur,
                        :notes
                    )
                """),
                {
                    "flow_date": row.flow_date,
                    "broker_name": row.broker_name,
                    "flow_type": row.flow_type,
                    "amount": row.amount,
                    "currency": row.currency,
                    "fx_rate_to_eur": row.fx_rate_to_eur,
                    "notes": row.notes,
                },
            )

    print(f"Imported {len(df)} cash flow rows.")
    print("cash_flows table was replaced from CSV.")


if __name__ == "__main__":
    main()
