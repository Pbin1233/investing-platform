from datetime import date

import pandas as pd
import yfinance as yf

from app.portfolio.xirr import (
    annualized_return,
    portfolio_cash_flows,
    calculate_portfolio_xirr,
)


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
        raise RuntimeError(f"No price for {symbol} near {target_date}")

    hist = hist[hist.index.date <= target_date]
    hist = hist.dropna(subset=["Close"])

    if hist.empty:
        raise RuntimeError(f"No price for {symbol} on or before {target_date}")

    return float(hist["Close"].iloc[-1])


def fetch_usd_to_eur_on_or_before(target_date: date) -> float:
    eur_usd = fetch_close_on_or_before("EURUSD=X", target_date)
    return 1 / eur_usd


def benchmark_xirr(
    symbol: str = DEFAULT_BENCHMARK,
    as_of_date: date | None = None,
) -> dict:
    if as_of_date is None:
        as_of_date = date.today()

    portfolio_result = calculate_portfolio_xirr(as_of_date=as_of_date)
    flows = portfolio_cash_flows(as_of_date=as_of_date)

    invest_flows = flows[flows["source"].isin(["DEPOSIT", "WITHDRAWAL"])].copy()

    units = 0.0
    benchmark_cash_flows = []

    for row in invest_flows.itertuples(index=False):
        benchmark_price_usd = fetch_close_on_or_before(symbol, row.flow_date)
        usd_to_eur = fetch_usd_to_eur_on_or_before(row.flow_date)

        benchmark_price_eur = benchmark_price_usd * usd_to_eur

        if row.source == "DEPOSIT":
            invested_eur = -row.amount_eur
            units += invested_eur / benchmark_price_eur
            benchmark_cash_flows.append(
                {
                    "flow_date": row.flow_date,
                    "amount_eur": row.amount_eur,
                    "source": "DEPOSIT",
                }
            )

        elif row.source == "WITHDRAWAL":
            withdrawn_eur = row.amount_eur
            units -= withdrawn_eur / benchmark_price_eur
            benchmark_cash_flows.append(
                {
                    "flow_date": row.flow_date,
                    "amount_eur": row.amount_eur,
                    "source": "WITHDRAWAL",
                }
            )

    terminal_price_usd = fetch_close_on_or_before(symbol, as_of_date)
    terminal_usd_to_eur = fetch_usd_to_eur_on_or_before(as_of_date)
    terminal_price_eur = terminal_price_usd * terminal_usd_to_eur
    terminal_value_eur = units * terminal_price_eur

    benchmark_cash_flows.append(
        {
            "flow_date": as_of_date,
            "amount_eur": terminal_value_eur,
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
        "benchmark_terminal_value_eur": float(terminal_value_eur),
        "spread": (
            portfolio_result["xirr"] - benchmark_return
            if portfolio_result["xirr"] is not None and benchmark_return is not None
            else None
        ),
        "fx_aware": True,
    }


def main():
    result = benchmark_xirr()

    print(f"Benchmark comparison: {result['symbol']}")
    print(f"as_of_date: {result['as_of_date']}")
    print(f"fx_aware: {result['fx_aware']}")
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
