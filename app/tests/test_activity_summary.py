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
