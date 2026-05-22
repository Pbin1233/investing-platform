from datetime import date

import pandas as pd
import yfinance as yf

from app.portfolio.xirr import annualized_return, portfolio_cash_flows, calculate_portfolio_xirr


DEFAULT_BENCHMARK = "SPY"


def fetch_close_on_or_before(symbol: str, target_date: date) -> float:
    start = pd.to_datetime(target_date) - pd.Timedelta(days=7)
    end = pd.to_datetime(target_date) + pd.Timedelta(days=1)

    hist = yf.Ticker(symbol).history(
        start=start.date().isoformat(),
        end=end.date().isoformat(),
        auto_adjust=True,
    )

    if hist.empty:
        raise RuntimeError(f"No benchmark price for {symbol} near {target_date}")

    hist = hist[hist.index.date <= target_date]

    if hist.empty:
        raise RuntimeError(f"No benchmark price on or before {target_date}")

    return float(hist["Close"].iloc[-1])


def benchmark_xirr(symbol: str = DEFAULT_BENCHMARK, as_of_date: date | None = None) -> dict:
    if as_of_date is None:
        as_of_date = date.today()

    portfolio_result = calculate_portfolio_xirr(as_of_date=as_of_date)
    flows = portfolio_cash_flows(as_of_date=as_of_date)

    invest_flows = flows[flows["source"].isin(["DEPOSIT", "WITHDRAWAL"])].copy()

    units = 0.0
    benchmark_cash_flows = []

    for row in invest_flows.itertuples(index=False):
        price = fetch_close_on_or_before(symbol, row.flow_date)

        if row.source == "DEPOSIT":
            invested = -row.amount_eur
            units += invested / price
            benchmark_cash_flows.append(
                {
                    "flow_date": row.flow_date,
                    "amount_eur": row.amount_eur,
                    "source": "DEPOSIT",
                }
            )

        elif row.source == "WITHDRAWAL":
            withdrawn = row.amount_eur
            units -= withdrawn / price
            benchmark_cash_flows.append(
                {
                    "flow_date": row.flow_date,
                    "amount_eur": row.amount_eur,
                    "source": "WITHDRAWAL",
                }
            )

    terminal_price = fetch_close_on_or_before(symbol, as_of_date)
    terminal_value = units * terminal_price

    benchmark_cash_flows.append(
        {
            "flow_date": as_of_date,
            "amount_eur": terminal_value,
            "source": "BENCHMARK_CURRENT_VALUE",
        }
    )

    benchmark_flows = pd.DataFrame(benchmark_cash_flows)
    benchmark_flows["flow_date"] = pd.to_datetime(benchmark_flows["flow_date"]).dt.date
    benchmark_flows["amount_eur"] = benchmark_flows["amount_eur"].astype(float)

    benchmark_return = annualized_return(benchmark_flows)

    return {
        "symbol": symbol,
        "as_of_date": as_of_date,
        "portfolio_xirr": portfolio_result["xirr"],
        "portfolio_terminal_value_eur": portfolio_result["terminal_value_eur"],
        "benchmark_xirr": benchmark_return,
        "benchmark_terminal_value_eur": float(terminal_value),
        "spread": (
            portfolio_result["xirr"] - benchmark_return
            if portfolio_result["xirr"] is not None and benchmark_return is not None
            else None
        ),
    }


def main():
    result = benchmark_xirr()

    print(f"Benchmark comparison: {result['symbol']}")
    print(f"as_of_date: {result['as_of_date']}")
    print(f"portfolio_terminal_value_eur: {result['portfolio_terminal_value_eur']:.2f}")
    print(f"benchmark_terminal_value_eur: {result['benchmark_terminal_value_eur']:.2f}")

    for key in ["portfolio_xirr", "benchmark_xirr", "spread"]:
        value = result[key]
        if value is None:
            print(f"{key}: not available")
        else:
            print(f"{key}: {value * 100:.2f}%")


if __name__ == "__main__":
    main()
