import pandas as pd

from app.portfolio.yearly_summary import (
    _add_tax_estimates,
    _summarize_realized_gains,
)


def test_add_tax_estimates_offsets_dividend_withholding_and_adds_ivafe():
    summary = pd.DataFrame(
        [
            {
                "year": 2024,
                "gross_dividends_eur": 100.0,
                "withholding_tax_eur": 15.0,
                "realized_gain_eur": 200.0,
                "year_end_market_value_eur": 10_000.0,
            }
        ]
    )

    result = _add_tax_estimates(summary).iloc[0]

    assert result["taxable_realized_gain_eur"] == 200.0
    assert result["capital_gains_tax_eur"] == 52.0
    assert result["dividend_tax_eur"] == 26.0
    assert result["dividend_withholding_credit_eur"] == 15.0
    assert result["dividend_tax_due_after_withholding_eur"] == 11.0
    assert result["ivafe_tax_eur"] == 20.0
    assert result["estimated_total_tax_liability_eur"] == 98.0
    assert result["estimated_tax_due_after_withholding_eur"] == 83.0


def test_add_tax_estimates_does_not_tax_negative_realized_gains():
    summary = pd.DataFrame(
        [
            {
                "year": 2024,
                "gross_dividends_eur": 100.0,
                "withholding_tax_eur": 30.0,
                "realized_gain_eur": -50.0,
                "year_end_market_value_eur": 0.0,
            }
        ]
    )

    result = _add_tax_estimates(summary).iloc[0]

    assert result["taxable_realized_gain_eur"] == 0.0
    assert result["capital_gains_tax_eur"] == 0.0
    assert result["dividend_tax_eur"] == 26.0
    assert result["dividend_withholding_credit_eur"] == 26.0
    assert result["dividend_tax_due_after_withholding_eur"] == 0.0
    assert result["estimated_tax_due_after_withholding_eur"] == 0.0


def test_summarize_realized_gains_groups_proceeds_cost_basis_and_gain():
    gains = pd.DataFrame(
        [
            {
                "broker_name": "IB",
                "ticker": "AVGO",
                "sell_date": "2026-01-10",
                "proceeds_eur": 150.0,
                "cost_basis_eur": 100.0,
                "realized_gain_eur": 50.0,
            },
            {
                "broker_name": "DEGIRO",
                "ticker": "ASML",
                "sell_date": "2026-03-10",
                "proceeds_eur": 200.0,
                "cost_basis_eur": 240.0,
                "realized_gain_eur": -40.0,
            },
        ]
    )

    result = _summarize_realized_gains(gains).iloc[0]

    assert result["year"] == 2026
    assert result["realized_proceeds_eur"] == 350.0
    assert result["realized_cost_basis_eur"] == 340.0
    assert result["realized_gain_eur"] == 10.0


def test_summarize_realized_gains_can_group_by_broker():
    gains = pd.DataFrame(
        [
            {
                "broker_name": "IB",
                "ticker": "AVGO",
                "sell_date": "2026-01-10",
                "proceeds_eur": 150.0,
                "cost_basis_eur": 100.0,
                "realized_gain_eur": 50.0,
            },
            {
                "broker_name": "DEGIRO",
                "ticker": "ASML",
                "sell_date": "2026-03-10",
                "proceeds_eur": 200.0,
                "cost_basis_eur": 240.0,
                "realized_gain_eur": -40.0,
            },
        ]
    )

    result = _summarize_realized_gains(gains, by_broker=True)
    ib = result[result["broker_name"] == "IB"].iloc[0]
    degiro = result[result["broker_name"] == "DEGIRO"].iloc[0]

    assert ib["realized_proceeds_eur"] == 150.0
    assert ib["realized_cost_basis_eur"] == 100.0
    assert ib["realized_gain_eur"] == 50.0
    assert degiro["realized_proceeds_eur"] == 200.0
    assert degiro["realized_cost_basis_eur"] == 240.0
    assert degiro["realized_gain_eur"] == -40.0
