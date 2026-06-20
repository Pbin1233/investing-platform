from datetime import date

import pandas as pd

from app.portfolio import xirr


def _fake_read_sql(query, engine):
    sql = str(query)
    if "FROM cash_flows" in sql:
        return pd.DataFrame(
            [
                {
                    "broker_name": "IB",
                    "flow_date": date(2026, 1, 1),
                    "amount_eur": -1000.0,
                    "source": "DEPOSIT",
                }
            ]
        )

    if "FROM dividends" in sql:
        return pd.DataFrame(
            [
                {
                    "broker_name": "IB",
                    "flow_date": date(2026, 6, 1),
                    "amount_eur": 10.0,
                    "source": "DIVIDEND",
                },
                {
                    "broker_name": "INTESA",
                    "flow_date": date(2026, 6, 1),
                    "amount_eur": 50.0,
                    "source": "DIVIDEND",
                },
            ]
        )

    raise AssertionError(f"Unexpected query: {sql}")


def _fake_portfolio():
    return pd.DataFrame(
        [
            {
                "broker_name": "IB",
                "ticker": "SPY",
                "market_value_eur": 1100.0,
            },
            {
                "broker_name": "INTESA",
                "ticker": "IT0005532715",
                "market_value_eur": 25000.0,
            },
        ]
    )


def test_portfolio_xirr_flows_exclude_brokers_without_external_cash_history(monkeypatch):
    monkeypatch.setattr(xirr, "get_engine", lambda: object())
    monkeypatch.setattr(xirr.pd, "read_sql", _fake_read_sql)
    monkeypatch.setattr(xirr, "calculate_portfolio", _fake_portfolio)

    flows = xirr.portfolio_cash_flows(as_of_date=date(2026, 6, 20))

    assert flows["amount_eur"].tolist() == [-1000.0, 10.0, 1100.0]
    assert "INTESA" not in set(flows["broker_name"].dropna())


def test_broker_xirr_flows_exclude_unfunded_broker_terminal_values(monkeypatch):
    monkeypatch.setattr(xirr, "get_engine", lambda: object())
    monkeypatch.setattr(xirr.pd, "read_sql", _fake_read_sql)
    monkeypatch.setattr(xirr, "calculate_portfolio", _fake_portfolio)

    flows = xirr.broker_cash_flows(as_of_date=date(2026, 6, 20))

    assert set(flows["broker_name"]) == {"IB"}
    assert flows["amount_eur"].tolist() == [-1000.0, 10.0, 1100.0]
