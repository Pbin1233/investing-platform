from decimal import Decimal

from app.imports.import_ib_statement import parse_ib_statement


def test_parse_ib_statement_normalizes_trades_dividends_and_cash_flows(tmp_path):
    path = tmp_path / "ib.csv"
    path.write_text(
        "\n".join(
            [
                "Statement,Header,Field Name,Field Value",
                "Summary,Data,Base Currency,EUR",
                "Transaction History,Header,Date,Account,Description,Transaction Type,Symbol,Quantity,Price,Price Currency,Gross Amount ,Commission,Net Amount",
                "Transaction History,Data,2024-07-22,U123,Electronic Fund Transfer,Deposit,-,-,-,-,4000.0,-,4000.0",
                "Transaction History,Data,2024-07-30,U123,BROADCOM INC,Buy,AVGO,30.0,144.02,USD,-3995.04279,-0.92465,-3995.96744",
                "Transaction History,Data,2024-09-30,U123,AVGO Cash Dividend,Dividend,AVGO,-,-,-,15.084825,-,15.084825",
                "Transaction History,Data,2024-09-30,U123,AVGO US Tax,Foreign Tax Withholding,AVGO,-,-,-,-2.266985,-,-2.266985",
                "Transaction History,Data,2024-07-30,U123,FX row,Forex Trade Component,EUR.USD,1,1.08,USD,0,-,0",
            ]
        ),
        encoding="utf-8",
    )

    parsed = parse_ib_statement(path)

    assert len(parsed.transactions) == 1
    assert len(parsed.dividends) == 1
    assert len(parsed.cash_flows) == 1
    assert len(parsed.ignored) == 1

    trade = parsed.transactions.iloc[0]
    assert trade["ticker"] == "AVGO"
    assert trade["action"] == "BUY"
    assert trade["quantity"] == Decimal("30.0")
    assert trade["currency"] == "USD"
    assert trade["fx_rate_to_eur"] == Decimal("3995.04279") / Decimal("4320.600")
    assert trade["fees"] == Decimal("0.92465") / trade["fx_rate_to_eur"]

    dividend = parsed.dividends.iloc[0]
    assert dividend["ticker"] == "AVGO"
    assert dividend["gross_amount"] == Decimal("15.084825")
    assert dividend["withholding_tax"] == Decimal("2.266985")
    assert dividend["net_amount"] == Decimal("12.817840")

    cash_flow = parsed.cash_flows.iloc[0]
    assert cash_flow["flow_type"] == "DEPOSIT"
    assert cash_flow["amount"] == Decimal("4000.0")
