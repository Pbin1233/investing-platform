import pandas as pd
from sqlalchemy import text

from app.database.connection import get_engine


def get_universe(active_only: bool = True) -> pd.DataFrame:
    engine = get_engine()

    query = """
        SELECT
            s.ticker,
            COALESCE(MAX(t.asset_name), s.ticker) AS asset_name,
            s.price_symbol,
            s.quote_currency
        FROM securities s
        LEFT JOIN transactions t
            ON t.ticker = s.ticker
    """

    if active_only:
        query += """
            WHERE EXISTS (
                SELECT 1
                FROM transactions tx
                WHERE tx.ticker = s.ticker
            )
        """

    query += """
        GROUP BY
            s.ticker,
            s.price_symbol,
            s.quote_currency
        ORDER BY s.ticker
    """

    df = pd.read_sql(
        text(query),
        engine,
    )

    return df


def enrich_universe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    sector_map = {
        "ASML": "Semiconductors",
        "AVGO": "Semiconductors",
        "NVDA": "Semiconductors",
        "QRVO": "Semiconductors",
    }

    geography_map = {
        "ASML": "Europe",
        "AVGO": "United States",
        "NVDA": "United States",
        "QRVO": "United States",
    }

    style_map = {
        "ASML": "Compounder",
        "AVGO": "Dividend Growth",
        "NVDA": "Growth",
        "QRVO": "Value",
    }

    df = df.copy()

    df["sector"] = df["ticker"].map(sector_map)
    df["geography"] = df["ticker"].map(geography_map)
    df["style"] = df["ticker"].map(style_map)

    return df


def build_universe(active_only: bool = True) -> pd.DataFrame:
    df = get_universe(active_only=active_only)
    df = enrich_universe(df)

    return df


def main():
    df = build_universe()

    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
