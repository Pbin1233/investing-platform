import os
from decimal import Decimal

import pandas as pd
from sqlalchemy import create_engine, text

from cost_basis import Trade, lifo_realized_gains


DB_USER = os.getenv("POSTGRES_USER", "investing")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "change_this_password")
DB_NAME = os.getenv("POSTGRES_DB", "investing")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@postgres:5432/{DB_NAME}"


def get_engine():
    return create_engine(DATABASE_URL)


def fetch_trades(engine, broker_name: str, ticker: str) -> list[Trade]:
    query = text("""
        SELECT trade_date, action, quantity, price, fees, fx_rate_to_eur
        FROM transactions
        WHERE broker_name = :broker_name
          AND ticker = :ticker
        ORDER BY trade_date, transaction_id
    """)

    df = pd.read_sql(
        query,
        engine,
        params={"broker_name": broker_name, "ticker": ticker},
    )

    trades = []
    for row in df.itertuples(index=False):
        trades.append(
            Trade(
                trade_date=str(row.trade_date),
                action=row.action,
                quantity=Decimal(str(row.quantity)),
                price=Decimal(str(row.price)),
                fees=Decimal(str(row.fees)),
                fx_rate_to_eur=Decimal(str(row.fx_rate_to_eur)),
            )
        )

    return trades


def calculate_all_realized_gains() -> pd.DataFrame:
    engine = get_engine()

    pairs = pd.read_sql(
        text("""
            SELECT DISTINCT broker_name, ticker
            FROM transactions
            ORDER BY broker_name, ticker
        """),
        engine,
    )

    rows = []

    for pair in pairs.itertuples(index=False):
        trades = fetch_trades(engine, pair.broker_name, pair.ticker)
        gains = lifo_realized_gains(trades)

        for gain in gains:
            rows.append({
                "broker_name": pair.broker_name,
                "ticker": pair.ticker,
                "sell_date": gain.sell_date,
                "quantity": gain.quantity,
                "proceeds_eur": gain.proceeds_eur,
                "cost_basis_eur": gain.cost_basis_eur,
                "realized_gain_eur": gain.realized_gain_eur,
            })

    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = calculate_all_realized_gains()

    if df.empty:
        print("No realized gains found.")
    else:
        print(df.to_string(index=False))
