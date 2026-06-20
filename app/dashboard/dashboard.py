import pandas as pd
import streamlit as st
from sqlalchemy import text

from app.database.connection import get_engine
from app.market_data.health import load_market_data_health, market_data_health_summary
from app.market_data.market_hours import market_sync_blockers_for_active_securities
from app.market_data.price_analytics import calculate_price_analytics
from app.ops.data_quality import run_all_checks
from app.ops.job_run_summary import build_job_run_summary_rows
from app.ops.system_health import build_system_health_rows, latest_backup_info
from app.portfolio.allocation import (
    allocation_by_broker,
    allocation_by_ticker,
    concentration_metrics,
)
from app.portfolio.activity_summary import (
    build_activity_snapshot,
    build_monthly_activity,
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
    build_tax_component_rows,
    build_tax_summary_table,
    calculate_yearly_summary,
    calculate_yearly_summary_by_broker,
)
from app.research.ideas.ideas import build_research_ideas, research_summary


st.set_page_config(page_title="Investing Platform", layout="wide")

st.markdown(
    """
    <style>
    :root {
        --panel-bg: rgba(127, 127, 127, 0.08);
        --panel-bg-strong: rgba(127, 127, 127, 0.12);
        --border: rgba(127, 127, 127, 0.28);
        --accent: var(--primary-color, #1f6feb);
        --metric-shadow: none;
    }

    .block-container {
        padding-top: 1.75rem;
        padding-bottom: 3rem;
        max-width: 1480px;
    }

    .app-header {
        background: linear-gradient(180deg, var(--panel-bg-strong) 0%, var(--panel-bg) 100%);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 1.15rem 1.35rem;
        margin-bottom: 1rem;
    }

    .app-title {
        color: inherit;
        font-size: 1.65rem;
        font-weight: 700;
        line-height: 1.15;
        margin: 0;
    }

    .app-subtitle {
        color: inherit;
        font-size: 0.92rem;
        margin-top: 0.25rem;
        opacity: 0.72;
    }

    div[data-testid="stMetric"] {
        background: var(--panel-bg);
        border: 1px solid var(--border);
        border-left: 3px solid var(--accent);
        border-radius: 8px;
        padding: 0.85rem 0.9rem;
        box-shadow: var(--metric-shadow);
    }

    div[data-testid="stMetric"] label {
        color: inherit !important;
        font-size: 0.78rem !important;
        font-weight: 600 !important;
        letter-spacing: 0 !important;
        opacity: 0.72;
    }

    h1, h2, h3 {
        color: inherit;
        letter-spacing: 0;
    }

    h2 {
        padding-top: 0.3rem;
    }

    h3 {
        border-top: 1px solid var(--border);
        padding-top: 1rem;
        margin-top: 1.4rem;
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid var(--border);
        border-radius: 8px;
        overflow: hidden;
        background: transparent;
    }

    div[data-testid="stTabs"] button {
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="app-header">
        <div class="app-title">Investing Platform</div>
        <div class="app-subtitle">
            Portfolio accounting, market data health, broker imports, and tax audit.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

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


def _is_numeric_like(series: pd.Series) -> bool:
    if pd.api.types.is_numeric_dtype(series):
        return True

    converted = pd.to_numeric(series, errors="coerce")
    return converted.notna().any()


def table_column_config(df: pd.DataFrame) -> dict:
    config = {}

    for column in df.columns:
        lower = str(column).lower()
        series = df[column]

        if lower.endswith("_at"):
            config[column] = st.column_config.DatetimeColumn(
                str(column),
                format="YYYY-MM-DD HH:mm",
            )
        elif "date" in lower:
            config[column] = st.column_config.DateColumn(
                str(column),
                format="YYYY-MM-DD",
            )
        elif lower in {"status", "mode", "action", "broker", "broker_name"}:
            config[column] = st.column_config.TextColumn(str(column), width="small")
        elif _is_numeric_like(series):
            if lower.endswith("_pct") or lower.endswith("pct"):
                config[column] = st.column_config.NumberColumn(
                    str(column),
                    format="%.2f%%",
                )
            elif lower.endswith("_eur") or "amount_eur" in lower:
                config[column] = st.column_config.NumberColumn(
                    str(column),
                    format="€ %.2f",
                )
            elif "quantity" in lower:
                config[column] = st.column_config.NumberColumn(
                    str(column),
                    format="%.6f",
                )
            elif "age" in lower or "count" in lower or lower.endswith("_rows"):
                config[column] = st.column_config.NumberColumn(
                    str(column),
                    format="%.1f",
                )
            else:
                config[column] = st.column_config.NumberColumn(
                    str(column),
                    format="%.4f",
                )

    return config


def display_table(df: pd.DataFrame, **kwargs) -> None:
    kwargs.setdefault("width", "stretch")
    kwargs.setdefault("hide_index", True)

    if isinstance(df, pd.DataFrame) and not df.empty:
        kwargs.setdefault("column_config", table_column_config(df))

    st.dataframe(df, **kwargs)


def display_table_expander(label: str, df: pd.DataFrame, expanded: bool = False) -> None:
    with st.expander(label, expanded=expanded):
        display_table(df, width="stretch", hide_index=True)


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
market_health = load_market_data_health(engine)
health_summary = market_data_health_summary(market_health)
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
checks = run_all_checks()
backup_info = latest_backup_info()
system_health = build_system_health_rows(
    latest_jobs,
    market_health,
    checks,
    backup_info,
)
system_status_counts = system_health["status"].value_counts()

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

    st.subheader("System Snapshot")
    latest_maintenance = latest_jobs[
        latest_jobs["job_name"] == "daily_maintenance"
    ]
    latest_maintenance_age = (
        None
        if latest_maintenance.empty
        else latest_maintenance.iloc[0]["age_hours"]
    )

    snap_col1, snap_col2, snap_col3, snap_col4 = st.columns(4)
    snap_col1.metric("Health OK", int(system_status_counts.get("OK", 0)))
    snap_col2.metric(
        "Needs Check",
        int(system_status_counts.get("CHECK", 0))
        + int(system_status_counts.get("MISSING", 0)),
    )
    snap_col3.metric(
        "Market Data",
        f"{health_summary['ok']}/{health_summary['active_securities']} OK",
    )
    snap_col4.metric(
        "Maintenance Age",
        "n/a" if pd.isna(latest_maintenance_age) else f"{latest_maintenance_age} h",
    )

    if set(system_health["status"]) == {"OK"}:
        st.success("Operations, market data, imports, and backups are currently OK.")
    else:
        st.warning("One or more operational areas need attention.")

    display_table(
        system_health[["area", "status", "detail"]],
        width="stretch",
        hide_index=True,
    )

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
        col3.metric("Total Value EUR", money(total_account))
        col4.metric("Tax Due EUR", money(latest_tax_due))

        st.subheader("Accounts")
        display_table(
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
        display_table(
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

        st.subheader("Position Summary")
        display_table(
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
                    "price_date",
                ]
            ].sort_values("market_value_eur", ascending=False),
            width="stretch",
            hide_index=True,
        )

        st.subheader("Top Holdings")
        top_holdings_chart = (
            holdings
            .sort_values("market_value_eur", ascending=False)
            .head(10)
            .set_index("ticker")[["market_value_eur", "invested_eur"]]
        )
        st.bar_chart(top_holdings_chart)

        display_table_expander(
            "Pricing and FX details",
            holdings[
                [
                    "broker_name",
                    "ticker",
                    "quantity",
                    "close_price",
                    "currency",
                    "fx_rate_to_eur",
                    "price_date",
                    "market_value_eur",
                    "invested_eur",
                    "unrealized_pl_eur",
                    "unrealized_pl_pct",
                ]
            ].sort_values("market_value_eur", ascending=False),
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
            display_table(
                ticker_alloc.head(10),
                width="stretch",
                hide_index=True,
            )
            if len(ticker_alloc) > 10:
                display_table_expander("All ticker allocations", ticker_alloc)

        broker_alloc = allocation_by_broker()
        if not broker_alloc.empty:
            st.subheader("Broker Allocation")
            display_table(broker_alloc, width="stretch", hide_index=True)


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
            display_table(performance_history, width="stretch", hide_index=True)

    st.subheader("Broker XIRR")
    broker_xirr = calculate_broker_xirr()

    if broker_xirr.empty:
        st.info("No broker XIRR data yet.")
    else:
        broker_display = add_pct_column(broker_xirr, "xirr", "xirr_pct")
        display_table(
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
        display_table(
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
            "Dividend Tax Due",
            money(latest["dividend_tax_due_after_withholding_eur"]),
        )
        col4.metric(
            "Estimated Due",
            money(latest["estimated_tax_due_after_withholding_eur"]),
        )

        st.subheader("Tax Summary")
        tax_summary = build_tax_summary_table(yearly_summary)
        if not tax_summary.empty:
            tax_chart = (
                tax_summary
                .sort_values("year")
                .set_index("year")[
                    [
                        "capital_gains_tax_eur",
                        "dividend_tax_due_after_withholding_eur",
                        "ivafe_tax_eur",
                    ]
                ]
            )
            st.bar_chart(tax_chart)
        display_table(tax_summary, width="stretch", hide_index=True)

        st.subheader("Latest Year Breakdown")
        latest_tax_components = build_tax_component_rows(latest)
        st.bar_chart(
            latest_tax_components.set_index("component")[["due_after_credits_eur"]]
        )
        display_table(latest_tax_components, width="stretch", hide_index=True)

        tax_columns = [
            "year",
            "realized_proceeds_eur",
            "realized_cost_basis_eur",
            "realized_gain_eur",
            "taxable_realized_gain_eur",
            "capital_gains_tax_eur",
            "gross_dividends_eur",
            "taxable_dividends_eur",
            "final_withholding_income_eur",
            "withholding_tax_eur",
            "creditable_withholding_tax_eur",
            "final_withholding_tax_eur",
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
        display_table_expander(
            "Full yearly tax calculation",
            yearly_summary[tax_columns],
        )

        broker_summary = calculate_yearly_summary_by_broker()
        if not broker_summary.empty:
            broker_tax_columns = [
                "year",
                "broker_name",
                "realized_proceeds_eur",
                "realized_cost_basis_eur",
                "realized_gain_eur",
                "taxable_realized_gain_eur",
                "capital_gains_tax_eur",
                "gross_dividends_eur",
                "taxable_dividends_eur",
                "final_withholding_income_eur",
                "withholding_tax_eur",
                "creditable_withholding_tax_eur",
                "final_withholding_tax_eur",
                "dividend_tax_due_after_withholding_eur",
                "year_end_market_value_eur",
                "year_end_unpriced_positions",
                "ivafe_tax_eur",
                "estimated_tax_due_after_withholding_eur",
            ]
            display_table_expander(
                "Full broker tax calculation",
                broker_summary[broker_tax_columns],
            )

        with st.expander("Tax assumptions"):
            display_table(
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
        gross_total = pd.to_numeric(dividend_filtered["gross_amount_eur"]).sum()
        withholding_total = pd.to_numeric(
            dividend_filtered["withholding_tax_eur"]
        ).sum()
        total_net = pd.to_numeric(dividend_filtered["net_amount_eur"]).sum()
        div_col1, div_col2, div_col3 = st.columns(3)
        div_col1.metric("Gross Dividends", money(gross_total))
        div_col2.metric("Withholding", money(withholding_total))
        div_col3.metric("Net Dividends", money(total_net))

        display_table(
            dividend_filtered.head(12),
            width="stretch",
            hide_index=True,
        )
        if len(dividend_filtered) > 12:
            display_table_expander("All filtered dividends", dividend_filtered)

    st.subheader("Realized Gains - LIFO")
    gains = calculate_all_realized_gains()

    if gains.empty:
        st.info("No realized gains found.")
    else:
        st.metric(
            "Total Realized Gain EUR",
            money(pd.to_numeric(gains["realized_gain_eur"]).sum()),
        )
        display_table(gains.head(12), width="stretch", hide_index=True)
        if len(gains) > 12:
            display_table_expander("All realized gains", gains)


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
        display_table(
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
            display_table(
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
            display_table(
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

    st.subheader("Activity Snapshot")
    snapshot = build_activity_snapshot(transactions, cash_flows, import_records)
    activity_cols = st.columns(4)
    activity_cols[0].metric("Transactions Loaded", int(snapshot["trade_count"]))
    activity_cols[1].metric("Latest Trade", snapshot["latest_trade"])
    activity_cols[2].metric("Net Cash Flow EUR", money(snapshot["net_flow_eur"]))
    activity_cols[3].metric("Latest Import", snapshot["latest_import"])
    st.caption(f"Latest import file: {snapshot['latest_import_file']}")

    monthly_activity = build_monthly_activity(
        transactions,
        cash_flows,
        import_records,
    )
    if monthly_activity.empty:
        st.info("No monthly activity yet.")
    else:
        st.subheader("Monthly Activity")
        monthly_chart = monthly_activity.sort_values("month").set_index("month")
        st.bar_chart(monthly_chart[["transactions", "cash_flows", "imported_rows"]])
        if "net_flow_eur" in monthly_chart.columns:
            st.bar_chart(monthly_chart[["net_flow_eur"]])
        display_table(monthly_activity, width="stretch", hide_index=True)

    st.subheader("Transactions")
    if transactions.empty:
        st.info("No transactions yet.")
    else:
        transaction_filtered = filter_frame(
            transactions,
            broker_key="transaction_broker",
            ticker_key="transaction_ticker",
            action_key="transaction_action",
        )
        action_counts = transaction_filtered["action"].value_counts()
        tx_col1, tx_col2, tx_col3, tx_col4 = st.columns(4)
        tx_col1.metric("Rows", len(transaction_filtered))
        tx_col2.metric("Buys", int(action_counts.get("BUY", 0)))
        tx_col3.metric("Sells", int(action_counts.get("SELL", 0)))
        tx_col4.metric("Splits", int(action_counts.get("SPLIT", 0)))

        display_table(
            transaction_filtered.head(15),
            width="stretch",
            hide_index=True,
        )
        if len(transaction_filtered) > 15:
            display_table_expander("All filtered transactions", transaction_filtered)

    st.subheader("Cash Flows")
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
        flow_totals = cash_flow_filtered.groupby("flow_type")["amount_eur"].sum()
        flow_col1, flow_col2, flow_col3 = st.columns(3)
        flow_col1.metric("Deposits", money(flow_totals.get("DEPOSIT", 0)))
        flow_col2.metric("Withdrawals", money(flow_totals.get("WITHDRAWAL", 0)))
        flow_col3.metric("Net Flow", money(cash_flow_filtered["amount_eur"].sum()))
        display_table(cash_flow_filtered.head(15), width="stretch", hide_index=True)
        if len(cash_flow_filtered) > 15:
            display_table_expander("All filtered cash flows", cash_flow_filtered)

    st.subheader("Recent Imports")
    if import_records.empty:
        st.info("No import records yet.")
    else:
        latest_imports = (
            import_records
            .sort_values("imported_at", ascending=False)
            .groupby("source_system", as_index=False)
            .first()
        )
        display_table(latest_imports, width="stretch", hide_index=True)
        display_table_expander("Recent import record details", import_records)


with market_tab:
    st.header("Market Data")

    st.subheader("Market Data Health")

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
        display_table(health_view, width="stretch", hide_index=True)

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

    display_table_expander("Latest price details", latest_prices)

    st.subheader("Historical Price Analytics")
    price_analytics = calculate_price_analytics()

    if price_analytics.empty:
        st.info("No historical price analytics available yet.")
    else:
        st.caption(
            "Returns, volatility, and drawdown are based on stored daily EUR-adjusted prices."
        )
        display_table(price_analytics.head(10), width="stretch", hide_index=True)
        if len(price_analytics) > 10:
            display_table_expander("All historical price analytics", price_analytics)


with ops_tab:
    st.header("Operations")

    st.subheader("System Health")
    health_cols = st.columns(4)
    health_cols[0].metric("OK areas", int(system_status_counts.get("OK", 0)))
    health_cols[1].metric("Check areas", int(system_status_counts.get("CHECK", 0)))
    health_cols[2].metric(
        "Missing areas",
        int(system_status_counts.get("MISSING", 0)),
    )
    health_cols[3].metric("Latest backup", backup_info["status"])

    if set(system_health["status"]) == {"OK"}:
        st.success("All monitored operational areas are OK.")
    else:
        st.warning("One or more operational areas need attention.")

    display_table(system_health, width="stretch", hide_index=True)

    st.subheader("Run Summary")

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

        latest_job_summary = build_job_run_summary_rows(latest_jobs)
        if latest_job_summary.empty:
            st.info("No readable job details found yet.")
        else:
            display_table(
                latest_job_summary,
                width="stretch",
                hide_index=True,
            )

        display_table_expander(
            "Raw latest job payloads",
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
        display_table(broker_imports, width="stretch", hide_index=True)

    st.subheader("Data Quality")
    quality_rows = []

    for name, df in checks.items():
        quality_rows.append(
            {
                "check": name,
                "status": "OK" if df.empty else "ISSUES",
                "rows": len(df),
            }
        )

    display_table(pd.DataFrame(quality_rows), width="stretch", hide_index=True)

    for name, df in checks.items():
        if not df.empty:
            with st.expander(f"{name} details"):
                display_table(df, width="stretch", hide_index=True)

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
        job_run_summary = build_job_run_summary_rows(job_runs)
        if job_run_summary.empty:
            st.info("No readable job run details found yet.")
        else:
            st.caption("Readable activity")
            display_table(job_run_summary.head(20), width="stretch", hide_index=True)
            if len(job_run_summary) > 20:
                display_table_expander("All readable job run details", job_run_summary)

        st.caption("Run log")
        display_table(
            job_runs[
                [
                    "id",
                    "job_name",
                    "status",
                    "rows_processed",
                    "started_at",
                    "completed_at",
                ]
            ].head(20),
            width="stretch",
            hide_index=True,
        )
        if len(job_runs) > 20:
            display_table_expander(
                "All recent job runs without payloads",
                job_runs[
                    [
                        "id",
                        "job_name",
                        "status",
                        "rows_processed",
                        "started_at",
                        "completed_at",
                    ]
                ],
            )
        display_table_expander("Raw recent job payloads", job_runs)
