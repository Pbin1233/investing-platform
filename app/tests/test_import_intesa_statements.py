from decimal import Decimal

from app.imports.import_intesa_statements import (
    BTP_TICKER,
    _parse_coupon,
    _parse_purchase,
    _parse_valuation,
)


def test_parse_purchase_from_confirmation_text():
    text = """
    CONFERMA OPERAZIONI IN TITOLI
    Codice e descrizione Titolo: 5532710 IT0005532715 BTPIT 14MZ28 2,00CUM
    Descrizione operazione : ACQUISTO ESECUZIONE DI ORDINI
    Valore nominale : 25.000,000 Div. emiss. :EUR
    PREZZO 100,000000 EUR 25.000,00
    Data di regolamento : 14/03/2023 Depositario dei Titoli: MONTE TITOLI SPA
    """

    result = _parse_purchase("confirmation.pdf", "abc123", text)

    assert result["trade_date"].isoformat() == "2023-03-14"
    assert result["ticker"] == BTP_TICKER
    assert result["quantity"] == Decimal("25000.000")
    assert result["price"] == Decimal("1.000000")
    assert result["action"] == "BUY"


def test_parse_coupon_from_coupon_notice_text():
    text = """
    CEDOLE, DIVIDENDI, PROVENTI e/o CAPITALE
    BTPIT 14MZ28 2,00CUM
    ISIN: IT0005532715
    Riepilogo degli eventi amministrativi del 16.09.2024 relativi agli strumenti finanziari presenti nel deposito
    Divisa emissione: EUR
    Interessi 251,36 EUR
    Indicizzazione capitale 136,25 EUR
    Ritenute italiane Aliquota: 12,50% -48,45 EUR
    Interessi da regolare in conto 339,16 EUR
    Totale interessi regolati con valuta 16.09.2024 339,16 EUR
    251,36 EUR
    136,25 EUR
    Aliquota: 12,50%
    -48,45 EUR
    339,16 EUR
    339,16 EUR
    Torino, 17 settembre 2024
    """

    result = _parse_coupon("coupon.pdf", "def456", text)

    assert result["payment_date"].isoformat() == "2024-09-16"
    assert result["ticker"] == BTP_TICKER
    assert result["net_amount"] == Decimal("339.16")
    assert result["withholding_tax"] == Decimal("48.45")
    assert result["gross_amount"] == Decimal("387.61")


def test_parse_valuation_from_rendiconto_text():
    text = """
    RENDICONTO TITOLI N.
    AL 31.03.2026
    DEPOSITO AMMINISTRATO N. 66355/3100/06472168
    Controvalore titoli e fondi
    +25 696,76 EUR
    Dettaglio deposito amministrato.
    5532710
    IT0005532715
    BTPIT 14MZ28 2,00CUM
    25 000,00 EUR
    Prezzo indicativo
    102,7870
    """

    result = _parse_valuation("statement.pdf", "ghi789", text)

    assert result["valuation_date"].isoformat() == "2026-03-31"
    assert result["ticker"] == BTP_TICKER
    assert result["quantity"] == Decimal("25000.00")
    assert result["market_value_eur"] == Decimal("25696.76")
