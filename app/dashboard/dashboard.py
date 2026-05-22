import pandas as pd
import streamlit as st
from sqlalchemy import text

from app.portfolio.realized_gains import calculate_all_realized_gains
from app.portfolio.portfolio_value import calculate_portfolio
from app.portfolio.broker_cash import calculate_broker_cash
from app.portfolio.yearly_summary import calculate_yearly_summary
from app.portfolio.xirr import calculate_portfolio_xirr, calculate_broker_xirr, calculate_position_xirr
from app.portfolio.benchmark import benchmark_xirr
from app.database.connection import get_engine


st.set_page_config(page_title="Investing Platform", layout="wide")
st.title("Investing Platform")

engine = get_engine()

def read_sql(query: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn)

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Dashboard",
    "Portfolio",
    "Transactions",
    "Dividends",
    "Realized Gains",
    "Yearly Summary",
])

with tab1:
    st.header("Account Summary")

    portfolio = calculate_portfolio()
    cash = calculate_broker_cash()

    if portfolio.empty and cash.empty:
        st.info("No data yet.")
    else:
        portfolio_by_broker = (
            portfolio
            .groupby("broker_name", as_index=False)["market_value_eur"]
            .sum()
            if not portfolio.empty
            else pd.DataFrame(columns=["broker_name", "market_value_eur"])
        )

        summary = cash.merge(
            portfolio_by_broker,
            on="broker_name",
            how="outer",
        ).fillna(0)

        summary["total_account_value_eur"] = (
            summary["cash_balance_eur"]
            + summary["market_value_eur"]
        )

        total_cash = summary["cash_balance_eur"].sum()
        total_securities = summary["market_value_eur"].sum()
        total_account = summary["total_account_value_eur"].sum()

        col1, col2, col3 = st.columns(3)
        col1.metric("Cash EUR", f"{total_cash:,.2f}")
        col2.metric("Securities EUR", f"{total_securities:,.2f}")
        col3.metric("Total Account Value EUR", f"{total_account:,.2f}")

        st.dataframe(summary, use_container_width=True)

    st.subheader("Performance")

    try:
        xirr_result = calculate_portfolio_xirr()
        benchmark_result = benchmark_xirr("SPY")

        perf_col1, perf_col2, perf_col3 = st.columns(3)

        portfolio_xirr = xirr_result["xirr"]
        benchmark_return = benchmark_result["benchmark_xirr"]
        spread = benchmark_result["spread"]

        perf_col1.metric(
            "Portfolio XIRR",
            "n/a" if portfolio_xirr is None else f"{portfolio_xirr * 100:,.2f}%"
        )
        perf_col2.metric(
            "SPY XIRR",
            "n/a" if benchmark_return is None else f"{benchmark_return * 100:,.2f}%"
        )
        perf_col3.metric(
            "Spread vs SPY",
            "n/a" if spread is None else f"{spread * 100:,.2f}%"
        )

        st.caption(
            "Benchmark comparison is FX-aware and uses the same external cash-flow dates."
        )

        broker_xirr = calculate_broker_xirr()

        if not broker_xirr.empty:
            broker_display = broker_xirr.copy()
            broker_display["xirr_pct"] = broker_display["xirr"].apply(
                lambda x: None if pd.isna(x) else x * 100
            )

            st.subheader("Broker Performance")
            st.dataframe(
                broker_display[
                    [
                        "broker_name",
                        "as_of_date",
                        "xirr_pct",
                        "cash_flow_count",
                        "terminal_value_eur",
                    ]
                ],
                use_container_width=True,
            )

    except Exception as exc:
        st.warning(f"Performance metrics unavailable: {exc}")

    st.subheader("Portfolio History")

    history = read_sql("""
        SELECT
            snapshot_date,
            SUM(market_value_eur) AS total_value_eur,
            SUM(invested_eur) AS total_invested_eur,
            SUM(unrealized_pl_eur) AS total_unrealized_eur
        FROM portfolio_snapshots
        GROUP BY snapshot_date
        ORDER BY snapshot_date
    """)

    if not history.empty:
        history["snapshot_date"] = pd.to_datetime(history["snapshot_date"])

        st.line_chart(
            history.set_index("snapshot_date")[
                ["total_value_eur", "total_invested_eur"]
            ]
        )

with tab2:
    st.header("Portfolio Valuation")

    portfolio = calculate_portfolio()

    if portfolio.empty:
        st.info("No portfolio data yet.")
    else:
        total_value = pd.to_numeric(portfolio["market_value_eur"]).sum()
        total_invested = pd.to_numeric(portfolio["invested_eur"]).sum()
        unrealized = pd.to_numeric(portfolio["unrealized_pl_eur"]).sum()
        unrealized_pct = unrealized / total_invested * 100 if total_invested else 0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Market Value EUR", f"{total_value:,.2f}")
        col2.metric("Invested EUR", f"{total_invested:,.2f}")
        col3.metric("Unrealized P/L EUR", f"{unrealized:,.2f}")
        col4.metric("Unrealized P/L %", f"{unrealized_pct:,.2f}%")

        st.dataframe(portfolio, use_container_width=True)

        st.subheader("Position XIRR")

        position_xirr = calculate_position_xirr()

        if position_xirr.empty:
            st.info("No position XIRR data yet.")
        else:
            position_display = position_xirr.copy()
            position_display["xirr_pct"] = position_display["xirr"].apply(
                lambda x: None if pd.isna(x) else x * 100
            )

            st.dataframe(
                position_display[
                    [
                        "ticker",
                        "as_of_date",
                        "xirr_pct",
                        "cash_flow_count",
                        "terminal_value_eur",
                    ]
                ],
                use_container_width=True,
            )

with tab3:
    st.header("Transactions")

    transactions = read_sql("""
        SELECT
            trade_date,
            broker_name,
            ticker,
            asset_name,
            action,
            quantity,
            price,
            fees,
            currency,
            fx_rate_to_eur
        FROM transactions
        ORDER BY trade_date DESC, transaction_id DESC
        LIMIT 1000
    """)

    st.dataframe(transactions, use_container_width=True)

with tab4:
    st.header("Dividends")

    dividends = read_sql("""
        SELECT
            payment_date,
            broker_name,
            ticker,
            gross_amount,
            withholding_tax,
            net_amount,
            currency,
            fx_rate_to_eur,
            net_amount * fx_rate_to_eur AS net_amount_eur
        FROM dividends
        ORDER BY payment_date DESC, dividend_id DESC
        LIMIT 1000
    """)

    if dividends.empty:
        st.info("No dividends yet.")
    else:
        total_net = pd.to_numeric(dividends["net_amount_eur"]).sum()
        st.metric("Total Net Dividends EUR", f"{total_net:,.2f}")
        st.dataframe(dividends, use_container_width=True)

with tab5:
    st.header("Realized Gains - LIFO")

    gains = calculate_all_realized_gains()

    if gains.empty:
        st.info("No realized gains found.")
    else:
        st.dataframe(gains, use_container_width=True)

        total_gain = pd.to_numeric(gains["realized_gain_eur"]).sum()
        estimated_tax = total_gain * 0.26

        col1, col2 = st.columns(2)
        col1.metric("Total Realized Gain EUR", f"{total_gain:,.2f}")
        col2.metric("Estimated 26% Tax EUR", f"{estimated_tax:,.2f}")


with tab6:
    st.header("Yearly Summary")

    summary = calculate_yearly_summary()

    if summary.empty:
        st.info("No yearly summary data available.")
    else:
        st.dataframe(summary, use_container_width=True)

        latest = summary.sort_values("year").iloc[-1]

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Latest Year Net Deposits EUR",
            f"{latest['net_external_cash_flow_eur']:,.2f}"
        )

        col2.metric(
            "Latest Year Dividends EUR",
            f"{latest['net_dividends_eur']:,.2f}"
        )

        col3.metric(
            "Estimated Tax EUR",
            f"{latest['estimated_capital_gains_tax_eur']:,.2f}"
        )
