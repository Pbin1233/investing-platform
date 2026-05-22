from datetime import date

import numpy_financial as npf
import pandas as pd
from sqlalchemy import text

from app.database.connection import get_engine
from app.portfolio.portfolio_value import calculate_portfolio


def annualized_return(cash_flows: pd.DataFrame) -> float | None:
    """
    Compute money-weighted annualized return from dated EUR cash flows.

    Convention:
    - negative = money invested into portfolio
    - positive = money returned from portfolio
    """
    if cash_flows.empty:
        return None

    cash_flows = cash_flows.sort_values("flow_date").copy()

    if not (cash_flows["amount_eur"] < 0).any():
        return None

    if not (cash_flows["amount_eur"] > 0).any():
        return None

    start = cash_flows["flow_date"].iloc[0]

    years = cash_flows["flow_date"].apply(
        lambda d: (d - start).days / 365.25
    )

    def npv(rate: float) -> float:
        return float(
            (cash_flows["amount_eur"] / ((1 + rate) ** years)).sum()
        )

    # Robust bisection over a wide but finite range.
    low = -0.9999
    high = 10.0

    try:
        low_value = npv(low)
        high_value = npv(high)

        if low_value * high_value > 0:
            return None

        for _ in range(100):
            mid = (low + high) / 2
            mid_value = npv(mid)

            if abs(mid_value) < 1e-8:
                return mid

            if low_value * mid_value <= 0:
                high = mid
                high_value = mid_value
            else:
                low = mid
                low_value = mid_value

        return (low + high) / 2

    except Exception:
        return None


def portfolio_cash_flows(as_of_date: date | None = None) -> pd.DataFrame:
    if as_of_date is None:
        as_of_date = date.today()

    engine = get_engine()

    external_flows = pd.read_sql(
        text("""
            SELECT
                flow_date,
                CASE
                    WHEN flow_type = 'DEPOSIT'
                    THEN -amount * fx_rate_to_eur
                    WHEN flow_type = 'WITHDRAWAL'
                    THEN amount * fx_rate_to_eur
                    ELSE 0
                END AS amount_eur,
                flow_type AS source
            FROM cash_flows
            WHERE flow_type IN ('DEPOSIT', 'WITHDRAWAL')
        """),
        engine,
    )

    dividends = pd.read_sql(
        text("""
            SELECT
                payment_date AS flow_date,
                net_amount * fx_rate_to_eur AS amount_eur,
                'DIVIDEND' AS source
            FROM dividends
        """),
        engine,
    )

    current_value = calculate_portfolio()["market_value_eur"].sum()

    terminal = pd.DataFrame(
        [{
            "flow_date": as_of_date,
            "amount_eur": float(current_value),
            "source": "CURRENT_VALUE",
        }]
    )

    flows = pd.concat(
        [external_flows, dividends, terminal],
        ignore_index=True,
    )

    flows["flow_date"] = pd.to_datetime(flows["flow_date"]).dt.date
    flows["amount_eur"] = flows["amount_eur"].astype(float)

    return flows[flows["amount_eur"] != 0].sort_values("flow_date")


def calculate_portfolio_xirr(as_of_date: date | None = None) -> dict:
    flows = portfolio_cash_flows(as_of_date=as_of_date)
    xirr = annualized_return(flows)

    return {
        "as_of_date": as_of_date or date.today(),
        "xirr": xirr,
        "cash_flow_count": len(flows),
        "terminal_value_eur": float(
            flows.loc[flows["source"] == "CURRENT_VALUE", "amount_eur"].sum()
        ),
    }


def main():
    result = calculate_portfolio_xirr()

    print("Portfolio XIRR")
    print(f"as_of_date: {result['as_of_date']}")
    print(f"cash_flow_count: {result['cash_flow_count']}")
    print(f"terminal_value_eur: {result['terminal_value_eur']:.2f}")

    if result["xirr"] is None:
        print("xirr: not available")
    else:
        print(f"xirr: {result['xirr'] * 100:.2f}%")


if __name__ == "__main__":
    main()
