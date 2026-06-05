import os
import sys

import pandas as pd
from sqlalchemy import text


from app.database.connection import get_engine

CSV_PATH = "/data/imports/transactions.csv"

REQUIRED_COLUMNS = [
    "trade_date",
    "broker_name",
    "ticker",
    "asset_name",
    "action",
    "quantity",
    "price",
    "fees",
    "currency",
    "fx_rate_to_eur",
    "notes",
]


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

    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df["broker_name"] = df["broker_name"].astype(str).str.strip()
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    df["asset_name"] = df["asset_name"].fillna("").astype(str).str.strip()
    df["action"] = df["action"].astype(str).str.strip().str.upper()
    df["currency"] = df["currency"].astype(str).str.strip().str.upper()
    df["notes"] = df["notes"].fillna("").astype(str)

    for col in ["quantity", "price", "fees", "fx_rate_to_eur"]:
        df[col] = pd.to_numeric(df[col], errors="raise")

    invalid_actions = sorted(set(df["action"]) - {"BUY", "SELL", "SPLIT"})
    if invalid_actions:
        print(f"Invalid actions: {invalid_actions}")
        sys.exit(1)

    if (df["quantity"] <= 0).any():
        print("Invalid quantity: all quantities must be positive.")
        sys.exit(1)

    if (df["price"] < 0).any():
        print("Invalid price: prices cannot be negative.")
        sys.exit(1)

    if (df["fx_rate_to_eur"] <= 0).any():
        print("Invalid fx_rate_to_eur: rates must be positive.")
        sys.exit(1)

    engine = get_engine()

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

        conn.execute(text("DELETE FROM transactions"))

        for row in df.itertuples(index=False):
            conn.execute(
                text("""
                    INSERT INTO transactions (
                        trade_date,
                        broker_name,
                        ticker,
                        asset_name,
                        action,
                        quantity,
                        price,
                        fees,
                        currency,
                        fx_rate_to_eur,
                        notes
                    )
                    VALUES (
                        :trade_date,
                        :broker_name,
                        :ticker,
                        :asset_name,
                        :action,
                        :quantity,
                        :price,
                        :fees,
                        :currency,
                        :fx_rate_to_eur,
                        :notes
                    )
                """),
                {
                    "trade_date": row.trade_date,
                    "broker_name": row.broker_name,
                    "ticker": row.ticker,
                    "asset_name": row.asset_name,
                    "action": row.action,
                    "quantity": row.quantity,
                    "price": row.price,
                    "fees": row.fees,
                    "currency": row.currency,
                    "fx_rate_to_eur": row.fx_rate_to_eur,
                    "notes": row.notes,
                },
            )

    print(f"Imported {len(df)} transactions.")
    print("Transactions table was replaced from CSV.")


if __name__ == "__main__":
    main()
