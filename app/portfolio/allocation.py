import pandas as pd

from app.portfolio.portfolio_value import calculate_portfolio
from app.portfolio.broker_cash import calculate_broker_cash


def allocation_by_ticker() -> pd.DataFrame:
    portfolio = calculate_portfolio()

    if portfolio.empty:
        return pd.DataFrame()

    df = portfolio.copy()

    total_value = df["market_value_eur"].sum()

    df["allocation_pct"] = (
        df["market_value_eur"] / total_value * 100
    )

    return df.sort_values(
        "allocation_pct",
        ascending=False,
    )[
        [
            "ticker",
            "broker_name",
            "market_value_eur",
            "allocation_pct",
        ]
    ]


def allocation_by_broker() -> pd.DataFrame:
    portfolio = calculate_portfolio()
    cash = calculate_broker_cash()

    portfolio_grouped = (
        portfolio.groupby("broker_name", as_index=False)[
            "market_value_eur"
        ].sum()
        if not portfolio.empty
        else pd.DataFrame(
            columns=["broker_name", "market_value_eur"]
        )
    )

    summary = cash.merge(
        portfolio_grouped,
        on="broker_name",
        how="outer",
    ).fillna(0)

    summary["total_value_eur"] = (
        summary["cash_balance_eur"]
        + summary["market_value_eur"]
    )

    total = summary["total_value_eur"].sum()

    summary["allocation_pct"] = (
        summary["total_value_eur"] / total * 100
    )

    return summary.sort_values(
        "allocation_pct",
        ascending=False,
    )


def concentration_metrics() -> dict:
    allocation = allocation_by_ticker()

    if allocation.empty:
        return {}

    weights = (
        allocation["allocation_pct"]
        .sort_values(ascending=False)
        .tolist()
    )

    return {
        "top_1_pct": weights[0],
        "top_3_pct": sum(weights[:3]),
        "position_count": len(weights),
    }


def main():
    print("\nAllocation by ticker\n")
    print(
        allocation_by_ticker().to_string(index=False)
    )

    print("\nAllocation by broker\n")
    print(
        allocation_by_broker().to_string(index=False)
    )

    print("\nConcentration metrics\n")
    print(concentration_metrics())


if __name__ == "__main__":
    main()
