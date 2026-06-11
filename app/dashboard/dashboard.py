import pandas as pd
import streamlit as st
from sqlalchemy import text

from app.database.connection import get_engine
from app.market_data.health import load_market_data_health, market_data_health_summary
from app.market_data.market_hours import market_sync_blockers_for_active_securities
from app.market_data.price_analytics import calculate_price_analytics
from app.ops.data_quality import run_all_checks
from app.portfolio.allocation import (
    allocation_by_broker,
    allocation_by_ticker,
    concentration_metrics,
)
from app.portfolio.benchmark import benchmark_xirr
from app.portfolio.broker_cash import calculate_broker_cash
from app.portfolio.performance_history import calculate_performance_history
from app.portfolio.portfolio_value import calculate_portfolio
from app.portfolio.realized_gains import calculate_all_realized_gains
from app.portfolio.xirr import (
    calculate_broker_xirr,
    calculate_portfolio_xirr,
    calculate_position_xirr,
)
from app.portfolio.yearly_summary import (
    CAPITAL_GAINS_TAX_RATE,
    DIVIDEND_TAX_RATE,
    IVAFE_TAX_RATE,
    calculate_yearly_summary,
    calculate_yearly_summary_by_broker,
)
from app.research.ideas.ideas import build_research_ideas, research_summary


st.set_page_config(page_title="Investing Platform", layout="wide")
st.title("Investing Platform")

engine = get_engine()


def read_sql(query: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn)


def money(value) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{float(value):,.2f}"


def percent(value) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{float(value):,.2f}%"


def xirr_percent(value) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value) * 100:,.2f}%"


def add_pct_column(df: pd.DataFrame, source_col: str, target_col: str) -> pd.DataFrame:
    df = df.copy()
    df[target_col] = df[source_col].apply(
        lambda value: None if pd.isna(value) else float(value) * 100
    )
    return df


def filter_frame(
    df: pd.DataFrame,
    broker_key: str,
    ticker_key: str | None = None,
    action_key: str | None = None,
) -> pd.DataFrame:
    if df.empty:
        return df

    filtered = df.copy()

    if "broker_name" in filtered.columns:
        brokers = ["All"] + sorted(filtered["broker_name"].dropna().unique())
        broker = st.selectbox("Broker", brokers, key=broker_key)
        if broker != "All":
            filtered = filtered[filtered["broker_name"] == broker]

    if ticker_key and "ticker" in filtered.columns:
        tickers = ["All"] + sorted(filtered["ticker"].dropna().unique())
        ticker = st.selectbox("Ticker", tickers, key=ticker_key)
        if ticker != "All":
            filtered = filtered[filtered["ticker"] == ticker]

    if action_key and "action" in filtered.columns:
        actions = ["All"] + sorted(filtered["action"].dropna().unique())
        action = st.selectbox("Action", actions, key=action_key)
        if action != "All":
            filtered = filtered[filtered["action"] == action]

    return filtered


portfolio = calculate_portfolio()
cash = calculate_broker_cash()
yearly_summary = calculate_yearly_summary()

overview_tab, holdings_tab, performance_tab, income_tab, research_tab, activity_tab, market_tab, ops_tab = st.tabs(
    [
        "Overview",
        "Holdings",
        "Performance",
        "Income & Taxes",
        "Research",
        "Activity",
        "Market Data",
        "Operations",
    ]
)


with overview_tab:
    st.header("Overview")

    portfolio_by_broker = (
        portfolio.groupby("broker_name", as_index=False)["market_value_eur"].sum()
        if not portfolio.empty
        else pd.DataFrame(columns=["broker_name", "market_value_eur"])
    )

    account_summary = cash.merge(
        portfolio_by_broker,
        on="broker_name",
        how="outer",
    ).fillna(0)

    if account_summary.empty:
        st.info("No account data yet.")
    else:
        account_summary["total_account_value_eur"] = (
            account_summary["cash_balance_eur"]
            + account_summary["market_value_eur"]
        )

        total_cash = account_summary["cash_balance_eur"].sum()
        total_securities = account_summary["market_value_eur"].sum()
        total_account = account_summary["total_account_value_eur"].sum()

        latest_tax_due = None
        if not yearly_summary.empty:
            latest_tax_due = yearly_summary.sort_values("year").iloc[-1][
                "estimated_tax_due_after_withholding_eur"
            ]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Cash EUR", money(total_cash))
        col2.metric("Securities EUR", money(total_securities))
        col3.metric("Total Account Value EUR", money(total_account))
        col4.metric("Latest Tax Due EUR", money(latest_tax_due))

        st.subheader("Accounts")
        st.dataframe(
            account_summary[
                [
                    "broker_name",
                    "cash_balance_eur",
                    "market_value_eur",
                    "total_account_value_eur",
                ]
            ].sort_values("total_account_value_eur", ascending=False),
            width="stretch",
            hide_index=True,
        )

    st.subheader("Performance Snapshot")

    try:
        xirr_result = calculate_portfolio_xirr()
        benchmark_result = benchmark_xirr("SPY")

        portfolio_xirr = xirr_result["xirr"]
        benchmark_return = benchmark_result["benchmark_xirr"]
        spread = benchmark_result["spread"]

        perf_col1, perf_col2, perf_col3 = st.columns(3)
        perf_col1.metric("Portfolio XIRR", xirr_percent(portfolio_xirr))
        perf_col2.metric("SPY XIRR", xirr_percent(benchmark_return))
        perf_col3.metric("Spread vs SPY", xirr_percent(spread))

        st.caption(
            "Benchmark comparison is FX-aware and uses the same external cash-flow dates."
        )

    except Exception as exc:
        st.warning(f"Performance metrics unavailable: {exc}")

    if not portfolio.empty:
        st.subheader("Largest Positions")
        largest_positions = portfolio.copy()
        total_value = largest_positions["market_value_eur"].sum()
        largest_positions["allocation_pct"] = (
            largest_positions["market_value_eur"] / total_value * 100
            if total_value
            else 0
        )
        st.dataframe(
            largest_positions[
                [
                    "broker_name",
                    "ticker",
                    "quantity",
                    "market_value_eur",
                    "allocation_pct",
                    "unrealized_pl_eur",
                    "unrealized_pl_pct",
                    "price_date",
                ]
            ].head(8),
            width="stretch",
            hide_index=True,
        )


with holdings_tab:
    st.header("Holdings")

    if portfolio.empty:
        st.info("No portfolio data yet.")
    else:
        holdings = portfolio.copy()
        total_value = pd.to_numeric(holdings["market_value_eur"]).sum()
        total_invested = pd.to_numeric(holdings["invested_eur"]).sum()
        unrealized = pd.to_numeric(holdings["unrealized_pl_eur"]).sum()
        unrealized_pct = unrealized / total_invested * 100 if total_invested else 0

        holdings["allocation_pct"] = (
            holdings["market_value_eur"] / total_value * 100
            if total_value
            else 0
        )

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Market Value EUR", money(total_value))
        col2.metric("Invested EUR", money(total_invested))
        col3.metric("Unrealized P/L EUR", money(unrealized))
        col4.metric("Unrealized P/L %", percent(unrealized_pct))

        st.subheader("Current Positions")
        st.dataframe(
            holdings[
                [
                    "broker_name",
                    "ticker",
                    "quantity",
                    "market_value_eur",
                    "allocation_pct",
                    "invested_eur",
                    "unrealized_pl_eur",
                    "unrealized_pl_pct",
                    "close_price",
                    "currency",
                    "fx_rate_to_eur",
                    "price_date",
                ]
            ],
            width="stretch",
            hide_index=True,
        )

        st.subheader("Allocation")

        concentration = concentration_metrics()
        if concentration:
            c1, c2, c3 = st.columns(3)
            c1.metric("Top Position", percent(concentration["top_1_pct"]))
            c2.metric("Top 3 Positions", percent(concentration["top_3_pct"]))
            c3.metric("Positions", f"{concentration['position_count']}")

        ticker_alloc = allocation_by_ticker()
        if not ticker_alloc.empty:
            st.dataframe(ticker_alloc, width="stretch", hide_index=True)

        broker_alloc = allocation_by_broker()
        if not broker_alloc.empty:
            st.subheader("Broker Allocation")
            st.dataframe(broker_alloc, width="stretch", hide_index=True)


with performance_tab:
    st.header("Performance")

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

    if history.empty:
        st.info("No portfolio snapshots yet.")
    else:
        history["snapshot_date"] = pd.to_datetime(history["snapshot_date"])
        st.line_chart(
            history.set_index("snapshot_date")[
                ["total_value_eur", "total_invested_eur"]
            ]
        )

    st.subheader("Drawdown")
    performance_history = calculate_performance_history()

    if performance_history.empty:
        st.info("No performance history yet.")
    else:
        st.line_chart(
            performance_history.set_index("snapshot_date")[
                ["total_value_eur", "running_peak_eur"]
            ]
        )
        st.line_chart(
            performance_history.set_index("snapshot_date")[
                ["drawdown_pct"]
            ]
        )

        with st.expander("Performance history table"):
            st.dataframe(performance_history, width="stretch", hide_index=True)

    st.subheader("Broker XIRR")
    broker_xirr = calculate_broker_xirr()

    if broker_xirr.empty:
        st.info("No broker XIRR data yet.")
    else:
        broker_display = add_pct_column(broker_xirr, "xirr", "xirr_pct")
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
            width="stretch",
            hide_index=True,
        )

    st.subheader("Position XIRR")
    position_xirr = calculate_position_xirr()

    if position_xirr.empty:
        st.info("No position XIRR data yet.")
    else:
        position_display = add_pct_column(position_xirr, "xirr", "xirr_pct")
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
            width="stretch",
            hide_index=True,
        )


with income_tab:
    st.header("Income & Taxes")
    st.caption(
        "Estimated taxes are an audit aid, not tax advice. Amounts are EUR-converted from stored broker data."
    )

    if yearly_summary.empty:
        st.info("No yearly summary data available.")
    else:
        latest = yearly_summary.sort_values("year").iloc[-1]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Tax Year", int(latest["year"]))
        col2.metric("Taxable Gains EUR", money(latest["taxable_realized_gain_eur"]))
        col3.metric(
            "Dividend Tax Due EUR",
            money(latest["dividend_tax_due_after_withholding_eur"]),
        )
        col4.metric(
            "Estimated Due EUR",
            money(latest["estimated_tax_due_after_withholding_eur"]),
        )

        st.subheader("Tax Calculation by Year")
        tax_columns = [
            "year",
            "realized_proceeds_eur",
            "realized_cost_basis_eur",
            "realized_gain_eur",
            "taxable_realized_gain_eur",
            "capital_gains_tax_eur",
            "gross_dividends_eur",
            "withholding_tax_eur",
            "net_dividends_eur",
            "dividend_tax_eur",
            "dividend_withholding_credit_eur",
            "dividend_tax_due_after_withholding_eur",
            "year_end_market_value_eur",
            "year_end_unpriced_positions",
            "ivafe_tax_eur",
            "estimated_total_tax_liability_eur",
            "estimated_tax_due_after_withholding_eur",
        ]
        st.dataframe(yearly_summary[tax_columns], width="stretch", hide_index=True)

        broker_summary = calculate_yearly_summary_by_broker()
        if not broker_summary.empty:
            st.subheader("Tax Calculation by Broker")
            broker_tax_columns = [
                "year",
                "broker_name",
                "realized_proceeds_eur",
                "realized_cost_basis_eur",
                "realized_gain_eur",
                "taxable_realized_gain_eur",
                "capital_gains_tax_eur",
                "gross_dividends_eur",
                "withholding_tax_eur",
                "dividend_tax_due_after_withholding_eur",
                "year_end_market_value_eur",
                "year_end_unpriced_positions",
                "ivafe_tax_eur",
                "estimated_tax_due_after_withholding_eur",
            ]
            st.dataframe(
                broker_summary[broker_tax_columns],
                width="stretch",
                hide_index=True,
            )

        with st.expander("Tax assumptions"):
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "assumption": "Capital gains tax rate",
                            "value": f"{CAPITAL_GAINS_TAX_RATE:.1%}",
                        },
                        {
                            "assumption": "Dividend tax rate",
                            "value": f"{DIVIDEND_TAX_RATE:.1%}",
                        },
                        {
                            "assumption": "IVAFE rate",
                            "value": f"{IVAFE_TAX_RATE:.2%}",
                        },
                        {
                            "assumption": "Cost basis method",
                            "value": "LIFO realized gains from imported broker trades",
                        },
                        {
                            "assumption": "Dividend withholding credit",
                            "value": "Capped at computed dividend tax for each year or broker row",
                        },
                        {
                            "assumption": "Year-end market value",
                            "value": "Position quantity at Dec 31 times latest stored price on or before Dec 31",
                        },
                        {
                            "assumption": "Unpriced positions",
                            "value": "Counted separately; missing year-end prices reduce IVAFE estimate",
                        },
                    ]
                ),
                width="stretch",
                hide_index=True,
            )

    st.subheader("Dividends")
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
            gross_amount * fx_rate_to_eur AS gross_amount_eur,
            withholding_tax * fx_rate_to_eur AS withholding_tax_eur,
            net_amount * fx_rate_to_eur AS net_amount_eur
        FROM dividends
        ORDER BY payment_date DESC, dividend_id DESC
        LIMIT 1000
    """)

    if dividends.empty:
        st.info("No dividends yet.")
    else:
        dividend_filtered = filter_frame(
            dividends,
            broker_key="dividend_broker",
            ticker_key="dividend_ticker",
        )
        total_net = pd.to_numeric(dividend_filtered["net_amount_eur"]).sum()
        st.metric("Filtered Net Dividends EUR", money(total_net))
        st.dataframe(dividend_filtered, width="stretch", hide_index=True)

    st.subheader("Realized Gains - LIFO")
    gains = calculate_all_realized_gains()

    if gains.empty:
        st.info("No realized gains found.")
    else:
        st.metric(
            "Total Realized Gain EUR",
            money(pd.to_numeric(gains["realized_gain_eur"]).sum()),
        )
        st.dataframe(gains, width="stretch", hide_index=True)


with research_tab:
    st.header("Research")
    st.caption(
        "Prototype watchlist and thesis tracker. Demo rows are illustrative and are not recommendations."
    )

    ideas = build_research_ideas()

    if ideas.empty:
        st.info("No research ideas yet.")
    else:
        summary = research_summary(ideas)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Ideas", f"{summary['idea_count']}")
        col2.metric("Owned", f"{summary['owned_count']}")
        col3.metric("Watchlist", f"{summary['watch_count']}")
        col4.metric(
            "Average Score",
            "n/a" if summary["avg_score"] is None else f"{summary['avg_score']:,.1f}",
        )

        filter_col1, filter_col2, filter_col3 = st.columns(3)
        statuses = ["All"] + sorted(ideas["status"].dropna().unique())
        themes = ["All"] + sorted(ideas["theme"].dropna().unique())
        regions = ["All"] + sorted(ideas["region"].dropna().unique())

        status = filter_col1.selectbox("Status", statuses, key="research_status")
        theme = filter_col2.selectbox("Theme", themes, key="research_theme")
        region = filter_col3.selectbox("Region", regions, key="research_region")

        filtered_ideas = ideas.copy()
        if status != "All":
            filtered_ideas = filtered_ideas[filtered_ideas["status"] == status]
        if theme != "All":
            filtered_ideas = filtered_ideas[filtered_ideas["theme"] == theme]
        if region != "All":
            filtered_ideas = filtered_ideas[filtered_ideas["region"] == region]

        st.subheader("Idea Pipeline")
        st.dataframe(
            filtered_ideas[
                [
                    "ticker",
                    "company",
                    "status",
                    "theme",
                    "region",
                    "idea_score",
                    "current_weight_pct",
                    "target_weight_pct",
                    "gap_to_target_pct",
                    "next_action",
                    "demo",
                ]
            ],
            width="stretch",
            hide_index=True,
        )

        with st.expander("Thesis notes"):
            st.dataframe(
                filtered_ideas[
                    [
                        "ticker",
                        "valuation_note",
                        "quality_note",
                        "risk_note",
                        "last_reviewed",
                    ]
                ],
                width="stretch",
                hide_index=True,
            )

        st.subheader("Target Gap")
        target_gap = filtered_ideas[
            filtered_ideas["target_weight_pct"] > 0
        ].sort_values("gap_to_target_pct", ascending=False)

        if target_gap.empty:
            st.info("No target weights set for the filtered ideas.")
        else:
            st.dataframe(
                target_gap[
                    [
                        "ticker",
                        "current_weight_pct",
                        "target_weight_pct",
                        "gap_to_target_pct",
                        "next_action",
                    ]
                ],
                width="stretch",
                hide_index=True,
            )


with activity_tab:
    st.header("Activity")

    st.subheader("Transactions")
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

    if transactions.empty:
        st.info("No transactions yet.")
    else:
        transaction_filtered = filter_frame(
            transactions,
            broker_key="transaction_broker",
            ticker_key="transaction_ticker",
            action_key="transaction_action",
        )
        st.dataframe(transaction_filtered, width="stretch", hide_index=True)

    st.subheader("Cash Flows")
    cash_flows = read_sql("""
        SELECT
            flow_date,
            broker_name,
            flow_type,
            amount,
            currency,
            fx_rate_to_eur,
            amount * fx_rate_to_eur AS amount_eur,
            notes
        FROM cash_flows
        ORDER BY flow_date DESC, cash_flow_id DESC
        LIMIT 1000
    """)

    if cash_flows.empty:
        st.info("No cash flows yet.")
    else:
        cash_flow_filtered = filter_frame(
            cash_flows,
            broker_key="cash_flow_broker",
        )
        flow_types = ["All"] + sorted(cash_flow_filtered["flow_type"].dropna().unique())
        flow_type = st.selectbox("Flow type", flow_types, key="cash_flow_type")
        if flow_type != "All":
            cash_flow_filtered = cash_flow_filtered[
                cash_flow_filtered["flow_type"] == flow_type
            ]
        st.dataframe(cash_flow_filtered, width="stretch", hide_index=True)

    st.subheader("Recent Imports")
    import_records = read_sql("""
        SELECT
            imported_at,
            source_system,
            source_file,
            target_table,
            target_id
        FROM import_records
        ORDER BY imported_at DESC, import_record_id DESC
        LIMIT 200
    """)

    if import_records.empty:
        st.info("No import records yet.")
    else:
        st.dataframe(import_records, width="stretch", hide_index=True)


with market_tab:
    st.header("Market Data")

    st.subheader("Market Data Health")
    market_health = load_market_data_health(engine)
    health_summary = market_data_health_summary(market_health)

    health_cols = st.columns(5)
    health_cols[0].metric("Active securities", health_summary["active_securities"])
    health_cols[1].metric("OK", health_summary["ok"])
    health_cols[2].metric("Stale", health_summary["stale"])
    health_cols[3].metric(
        "Missing/invalid",
        health_summary["missing"] + health_summary["invalid"],
    )
    health_cols[4].metric("Check", health_summary["check"])

    blockers = market_sync_blockers_for_active_securities(engine)
    if blockers:
        st.warning("Market sync blocked now: " + "; ".join(blockers))
    else:
        st.caption("Configured active markets are closed or outside the sync buffer now.")

    if market_health.empty:
        st.info("No active securities found.")
    else:
        health_view = market_health[
            [
                "ticker",
                "exchange",
                "quote_currency",
                "latest_price_date",
                "latest_price_age_days",
                "latest_daily_price_date",
                "latest_daily_age_days",
                "latest_source",
                "latest_daily_source",
                "status",
                "issues",
            ]
        ]
        st.dataframe(health_view, width="stretch", hide_index=True)

    st.subheader("Latest Prices")
    latest_prices = read_sql("""
        SELECT DISTINCT ON (s.ticker)
            s.ticker,
            s.price_symbol,
            s.exchange,
            s.quote_currency,
            p.price_date,
            p.close_price,
            p.currency,
            p.fx_rate_to_eur,
            p.close_price * p.fx_rate_to_eur AS close_price_eur
        FROM securities s
        LEFT JOIN prices p
          ON p.ticker = s.ticker
        WHERE s.active = TRUE
        ORDER BY s.ticker, p.price_date DESC NULLS LAST, p.price_id DESC NULLS LAST
    """)

    st.dataframe(latest_prices, width="stretch", hide_index=True)

    st.subheader("Historical Price Analytics")
    price_analytics = calculate_price_analytics()

    if price_analytics.empty:
        st.info("No historical price analytics available yet.")
    else:
        st.caption(
            "Returns, volatility, and drawdown are based on stored daily EUR-adjusted prices."
        )
        st.dataframe(price_analytics, width="stretch", hide_index=True)


with ops_tab:
    st.header("Operations")

    st.subheader("Run Summary")
    latest_jobs = read_sql("""
        SELECT DISTINCT ON (job_name)
            job_name,
            status,
            started_at,
            completed_at,
            rows_processed,
            ROUND(EXTRACT(EPOCH FROM (NOW() - started_at)) / 3600.0, 1)
                AS age_hours,
            message
        FROM job_runs
        ORDER BY job_name, started_at DESC
    """)

    if latest_jobs.empty:
        st.info("No maintenance runs logged yet.")
    else:
        latest_maintenance = latest_jobs[
            latest_jobs["job_name"] == "daily_maintenance"
        ]
        run_cols = st.columns(4)

        if latest_maintenance.empty:
            run_cols[0].metric("Daily maintenance", "n/a")
            run_cols[1].metric("Last run age", "n/a")
        else:
            latest_run = latest_maintenance.iloc[0]
            run_cols[0].metric("Daily maintenance", latest_run["status"])
            run_cols[1].metric("Last run age", f"{latest_run['age_hours']} h")

        failures = len(latest_jobs[latest_jobs["status"] == "failed"])
        running = len(latest_jobs[latest_jobs["status"] == "started"])
        run_cols[2].metric("Latest failed jobs", failures)
        run_cols[3].metric("Latest running jobs", running)

        st.dataframe(
            latest_jobs[
                [
                    "job_name",
                    "status",
                    "started_at",
                    "completed_at",
                    "age_hours",
                    "rows_processed",
                    "message",
                ]
            ],
            width="stretch",
            hide_index=True,
        )

    st.subheader("Broker Import Summary")
    broker_imports = read_sql("""
        WITH file_imports AS (
            SELECT
                source_system,
                source_file,
                COUNT(*) AS imported_rows,
                COUNT(*) FILTER (WHERE target_table = 'transactions')
                    AS transaction_rows,
                COUNT(*) FILTER (WHERE target_table = 'dividends')
                    AS dividend_rows,
                COUNT(*) FILTER (WHERE target_table = 'cash_flows')
                    AS cash_flow_rows,
                MIN(imported_at) AS first_imported_at,
                MAX(imported_at) AS latest_imported_at
            FROM import_records
            WHERE source_system IN ('IBKR', 'DEGIRO')
            GROUP BY source_system, source_file
        ),
        ranked AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY source_system
                    ORDER BY latest_imported_at DESC, source_file
                ) AS rn
            FROM file_imports
        )
        SELECT
            CASE
                WHEN source_system = 'IBKR' THEN 'IB'
                ELSE source_system
            END AS broker,
            source_system,
            source_file,
            imported_rows,
            transaction_rows,
            dividend_rows,
            cash_flow_rows,
            first_imported_at,
            latest_imported_at,
            ROUND(EXTRACT(EPOCH FROM (NOW() - latest_imported_at)) / 86400.0, 1)
                AS age_days
        FROM ranked
        WHERE rn = 1
        ORDER BY broker
    """)

    if broker_imports.empty:
        st.info("No broker import records found yet.")
    else:
        import_cols = st.columns(3)
        import_cols[0].metric("Broker feeds", len(broker_imports))
        import_cols[1].metric(
            "Latest import rows",
            int(broker_imports["imported_rows"].sum()),
        )
        import_cols[2].metric(
            "Oldest latest import",
            f"{broker_imports['age_days'].max()} d",
        )
        st.dataframe(broker_imports, width="stretch", hide_index=True)

    st.subheader("Data Quality")
    checks = run_all_checks()
    quality_rows = []

    for name, df in checks.items():
        quality_rows.append(
            {
                "check": name,
                "status": "OK" if df.empty else "ISSUES",
                "rows": len(df),
            }
        )

    st.dataframe(pd.DataFrame(quality_rows), width="stretch", hide_index=True)

    for name, df in checks.items():
        if not df.empty:
            with st.expander(f"{name} details"):
                st.dataframe(df, width="stretch", hide_index=True)

    st.subheader("Job Runs")
    job_runs = read_sql("""
        SELECT
            id,
            job_name,
            status,
            rows_processed,
            started_at,
            completed_at,
            message
        FROM job_runs
        ORDER BY started_at DESC
        LIMIT 100
    """)

    if job_runs.empty:
        st.info("No job runs yet.")
    else:
        st.dataframe(job_runs, width="stretch", hide_index=True)
