import pandas as pd

from app.portfolio.yearly_summary import _add_tax_estimates


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
