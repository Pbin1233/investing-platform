from decimal import Decimal

from app.imports.import_degiro_account import parse_degiro_account


def test_parse_degiro_account_normalizes_trade_group_dividends_and_deposits(tmp_path):
    path = tmp_path / "Account.csv"
    path.write_text(
        "\n".join(
            [
                "Date,Time,Value date,Product,ISIN,Description,FX,Change,,Balance,,Order Id",
                '02-04-2024,15:53,02-04-2024,BROADCOM INC,US11135F1012,Credito FX,"1,0736",USD,"3944,91",USD,"0,00",order-1',
                '02-04-2024,15:53,02-04-2024,BROADCOM INC,US11135F1012,Prelievo FX,,EUR,"-3674,44",EUR,"323,57",order-1',
                '02-04-2024,15:53,02-04-2024,BROADCOM INC,US11135F1012,DEGIRO costi di transazione e/o di terze parti,,EUR,"-2,00",EUR,"3998,01",order-1',
                '02-04-2024,15:53,02-04-2024,BROADCOM INC,US11135F1012,"Acquisto 3 Broadcom Inc@1.314,97 USD (US11135F1012)",,USD,"-3944,91",USD,"-3944,91",order-1',
                '16-04-2024,09:10,16-04-2024,,,Deposito flatex,,EUR,"4000,00",EUR,"4323,57",',
                '01-07-2024,07:39,28-06-2024,BROADCOM INC,US11135F1012,Dividendo,,USD,"15,75",USD,"13,81",',
                '01-07-2024,07:39,28-06-2024,BROADCOM INC,US11135F1012,Ritenuta sul dividendo,,USD,"-2,36",USD,"-1,94",',
                '02-07-2024,07:30,01-07-2024,,,Credito FX,,EUR,"12,83",EUR,"5134,34",',
                '02-07-2024,07:30,01-07-2024,,,Prelievo FX,"1,0767",USD,"-13,39",USD,"0,00",',
                '05-05-2024,18:02,30-04-2024,,,DEGIRO Costi di connessione 2024 (Nasdaq - NDQ),,EUR,"-2,50",EUR,"693,97",',
                '10-06-2024,10:51,10-06-2024,NVIDIA CORP,US67066G1040,"FRAZIONAMENTO AZIONARIO: 50 NVIDIA Corp @ 120,888 USD (US67066G1040)",,USD,"-6044,40",USD,"0,00",',
            ]
        ),
        encoding="utf-8",
    )

    parsed = parse_degiro_account(path)

    assert len(parsed.transactions) == 1
    assert len(parsed.dividends) == 1
    assert len(parsed.cash_flows) == 2
    assert len(parsed.ignored) == 6

    trade = parsed.transactions.iloc[0]
    assert trade["ticker"] == "AVGO"
    assert trade["action"] == "BUY"
    assert trade["quantity"] == Decimal("3")
    assert trade["price"] == Decimal("1314.97")
    assert trade["currency"] == "USD"
    assert trade["fx_rate_to_eur"] == Decimal("3674.44") / Decimal("3944.91")
    assert trade["fees"] == Decimal("2.00") / trade["fx_rate_to_eur"]

    dividend = parsed.dividends.iloc[0]
    assert dividend["ticker"] == "AVGO"
    assert dividend["gross_amount"] == Decimal("15.75")
    assert dividend["withholding_tax"] == Decimal("2.36")
    assert dividend["net_amount"] == Decimal("13.39")
    assert dividend["fx_rate_to_eur"] == Decimal("12.83") / Decimal("13.39")

    cash_flows = parsed.cash_flows.sort_values(["flow_type", "amount"])
    assert set(cash_flows["flow_type"]) == {"DEPOSIT", "FEE"}
