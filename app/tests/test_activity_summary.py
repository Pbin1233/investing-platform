import pandas as pd

from app.portfolio.activity_summary import (
    build_activity_snapshot,
    build_monthly_activity,
)


def test_build_activity_snapshot_summarizes_latest_dates_and_flows():
    transactions = pd.DataFrame(
        [
            {"trade_date": "2026-05-01", "action": "BUY"},
            {"trade_date": "2026-06-03", "action": "SELL"},
        ]
    )
    cash_flows = pd.DataFrame(
        [
            {"flow_date": "2026-06-01", "amount_eur": 1000.0},
            {"flow_date": "2026-06-02", "amount_eur": -150.0},
        ]
    )
    import_records = pd.DataFrame(
        [
            {
                "imported_at": "2026-06-01T10:00:00",
                "source_file": "old.csv",
            },
            {
                "imported_at": "2026-06-04T10:00:00",
                "source_file": "new.csv",
            },
        ]
    )

    result = build_activity_snapshot(transactions, cash_flows, import_records)

    assert result["trade_count"] == 2
    assert result["latest_trade"] == "2026-06-03"
    assert result["net_flow_eur"] == 850.0
    assert result["investment_flow_eur"] == 850.0
    assert result["latest_flow"] == "2026-06-02"
    assert result["latest_import"].startswith("2026-06-04")
    assert result["latest_import_file"] == "new.csv"


def test_build_monthly_activity_combines_sources():
    transactions = pd.DataFrame(
        [
            {"trade_date": "2026-06-01", "action": "BUY"},
            {"trade_date": "2026-06-02", "action": "BUY"},
            {"trade_date": "2026-06-03", "action": "SELL"},
            {"trade_date": "2026-05-01", "action": "SPLIT"},
        ]
    )
    cash_flows = pd.DataFrame(
        [
            {"flow_date": "2026-06-01", "amount_eur": 1000.0},
            {"flow_date": "2026-06-02", "amount_eur": -200.0},
            {"flow_date": "2026-05-02", "amount_eur": 300.0},
        ]
    )
    import_records = pd.DataFrame(
        [
            {"imported_at": "2026-06-04", "source_file": "ib.csv"},
            {"imported_at": "2026-06-05", "source_file": "ib.csv"},
            {"imported_at": "2026-05-03", "source_file": "degiro.csv"},
        ]
    )

    result = build_monthly_activity(transactions, cash_flows, import_records)
    june = result[result["month"] == "2026-06"].iloc[0]

    assert june["transactions"] == 3
    assert june["buys"] == 2
    assert june["sells"] == 1
    assert june["cash_flows"] == 2
    assert june["net_flow_eur"] == 800.0
    assert june["investment_flow_eur"] == 800.0
    assert june["imported_rows"] == 2
    assert june["import_files"] == 1


def test_build_monthly_activity_returns_empty_shape_for_no_data():
    result = build_monthly_activity(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())

    assert result.empty
    assert list(result.columns) == [
        "month",
        "transactions",
        "buys",
        "sells",
        "splits",
        "cash_flows",
        "net_flow_eur",
        "statement_investment_flow_eur",
        "investment_flow_eur",
        "imported_rows",
        "import_files",
    ]


def test_build_monthly_activity_ignores_invalid_dates():
    transactions = pd.DataFrame(
        [
            {"trade_date": "not-a-date", "action": "BUY"},
            {"trade_date": "2026-06-01", "action": "SELL"},
        ]
    )

    result = build_monthly_activity(transactions, pd.DataFrame(), pd.DataFrame())

    assert list(result["month"]) == ["2026-06"]
    assert result.iloc[0]["transactions"] == 1
    assert result.iloc[0]["sells"] == 1


def test_activity_counts_statement_funded_trades_as_investment_flow_only():
    transactions = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-01",
                "broker_name": "IB",
                "action": "BUY",
                "quantity": 10,
                "price": 100,
                "fees": 1,
                "fx_rate_to_eur": 1,
            },
            {
                "trade_date": "2026-06-02",
                "broker_name": "INTESA",
                "action": "BUY",
                "quantity": 25000,
                "price": 1,
                "fees": 0,
                "fx_rate_to_eur": 1,
            },
        ]
    )
    cash_flows = pd.DataFrame(
        [
            {
                "flow_date": "2026-06-01",
                "broker_name": "IB",
                "amount_eur": 28000,
            },
        ]
    )

    snapshot = build_activity_snapshot(transactions, cash_flows, pd.DataFrame())
    monthly = build_monthly_activity(transactions, cash_flows, pd.DataFrame())
    june = monthly[monthly["month"] == "2026-06"].iloc[0]

    assert snapshot["net_flow_eur"] == 28000.0
    assert snapshot["statement_investment_flow_eur"] == 25000.0
    assert snapshot["investment_flow_eur"] == 53000.0
    assert june["statement_investment_flow_eur"] == 25000.0
    assert june["investment_flow_eur"] == 53000.0


def test_activity_cash_flow_totals_ignore_non_investment_cash_rows():
    transactions = pd.DataFrame()
    cash_flows = pd.DataFrame(
        [
            {
                "flow_date": "2026-06-01",
                "broker_name": "DEGIRO",
                "flow_type": "DEPOSIT",
                "amount_eur": 12000,
            },
            {
                "flow_date": "2026-06-02",
                "broker_name": "DEGIRO",
                "flow_type": "FEE",
                "amount_eur": 10,
            },
        ]
    )

    snapshot = build_activity_snapshot(transactions, cash_flows, pd.DataFrame())
    monthly = build_monthly_activity(transactions, cash_flows, pd.DataFrame())

    assert snapshot["net_flow_eur"] == 12000.0
    assert snapshot["investment_flow_eur"] == 12000.0
    assert monthly.iloc[0]["cash_flows"] == 1
    assert monthly.iloc[0]["net_flow_eur"] == 12000.0
