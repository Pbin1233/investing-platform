import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from app.imports.import_ib_statement import (
    ParsedStatement,
    _combined_hash,
    _row_hash,
    import_statement,
    summarize,
)


SOURCE_SYSTEM = "DEGIRO"

ISIN_TO_TICKER = {
    "NL0010273215": "ASML",
    "US11135F1012": "AVGO",
    "US67066G1040": "NVDA",
    "US74736K1016": "QRVO",
}

TRADE_RE = re.compile(
    r"^(?P<kind>Acquisto|Vendita)\s+"
    r"(?P<quantity>[\d.,]+)\s+"
    r"(?P<name>.+)@"
    r"(?P<price>[\d.,]+)\s+"
    r"(?P<currency>[A-Z]{3})\s+"
    r"\((?P<isin>[^)]+)\)$"
)


@dataclass
class DegiroRow:
    row_number: int
    date: str
    time: str
    value_date: str
    product: str
    isin: str
    description: str
    fx: Decimal | None
    change_currency: str
    change_amount: Decimal | None
    balance_currency: str
    balance_amount: Decimal | None
    order_id: str
    source_hash: str


def _clean(value: str | None) -> str:
    if value is None:
        return ""

    return value.strip()


def _decimal(value: str | None) -> Decimal | None:
    value = _clean(value)
    if not value:
        return None

    normalized = value.replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid Degiro numeric value: {value}") from exc


def _date(value: str) -> str:
    day, month, year = value.split("-")
    return f"{year}-{month}-{day}"


def _ticker(isin: str, product: str) -> str:
    if isin in ISIN_TO_TICKER:
        return ISIN_TO_TICKER[isin]

    return product.strip().upper().replace(" ", ".")


def _note(source_file: str, row_numbers: list[int], description: str) -> str:
    rows = ",".join(str(row_number) for row_number in sorted(row_numbers))
    return f"DEGIRO import {source_file} rows {rows}: {description}"


def _read_rows(path: Path) -> list[DegiroRow]:
    rows = []
    source_file = path.name

    with path.open(newline="") as handle:
        reader = csv.reader(handle)
        next(reader)

        for row_number, row in enumerate(reader, start=2):
            padded = row + [""] * (12 - len(row))
            parsed = DegiroRow(
                row_number=row_number,
                date=_date(_clean(padded[0])),
                time=_clean(padded[1]),
                value_date=_date(_clean(padded[2])),
                product=_clean(padded[3]),
                isin=_clean(padded[4]),
                description=_clean(padded[5]),
                fx=_decimal(padded[6]),
                change_currency=_clean(padded[7]).upper(),
                change_amount=_decimal(padded[8]),
                balance_currency=_clean(padded[9]).upper(),
                balance_amount=_decimal(padded[10]),
                order_id=_clean(padded[11]),
                source_hash=_row_hash(source_file, row_number, row),
            )
            rows.append(parsed)

    return rows


def _group_by_order_id(rows: list[DegiroRow]) -> dict[str, list[DegiroRow]]:
    grouped: dict[str, list[DegiroRow]] = {}
    for row in rows:
        if row.order_id:
            grouped.setdefault(row.order_id, []).append(row)
    return grouped


def _fx_rate_from_order_group(trade: DegiroRow, group: list[DegiroRow]) -> Decimal:
    if trade.change_currency == "EUR":
        return Decimal("1")

    native_amount = abs(trade.change_amount or Decimal("0"))
    eur_amount = sum(
        (
            abs(row.change_amount or Decimal("0"))
            for row in group
            if row.change_currency == "EUR"
            and row.description in {"Credito FX", "Prelievo FX"}
        ),
        Decimal("0"),
    )

    if native_amount <= 0 or eur_amount <= 0:
        return Decimal("1")

    return eur_amount / native_amount


def _fees_from_order_group(fx_rate_to_eur: Decimal, group: list[DegiroRow]) -> Decimal:
    fee_eur = sum(
        (
            abs(row.change_amount or Decimal("0"))
            for row in group
            if row.change_currency == "EUR"
            and row.description.lower().startswith("degiro costi di transazione")
        ),
        Decimal("0"),
    )

    if fx_rate_to_eur <= 0:
        return fee_eur

    return fee_eur / fx_rate_to_eur


def _dividend_fx_rates(rows: list[DegiroRow]) -> dict[tuple[str, str], Decimal]:
    rates = {}
    grouped: dict[tuple[str, str], list[DegiroRow]] = {}

    for row in rows:
        if row.order_id:
            continue
        if row.description not in {"Credito FX", "Prelievo FX"}:
            continue
        grouped.setdefault((row.date, row.time), []).append(row)

    for group in grouped.values():
        eur_rows = [
            row for row in group
            if row.change_currency == "EUR" and (row.change_amount or Decimal("0")) > 0
        ]
        native_rows = [
            row for row in group
            if row.change_currency != "EUR" and (row.change_amount or Decimal("0")) < 0
        ]

        if len(eur_rows) != 1 or len(native_rows) != 1:
            continue

        eur_amount = eur_rows[0].change_amount or Decimal("0")
        native_amount = abs(native_rows[0].change_amount or Decimal("0"))
        if native_amount > 0:
            rates[(native_rows[0].change_currency, eur_rows[0].value_date)] = (
                eur_amount / native_amount
            )

    return rates


def parse_degiro_account(path: str | Path, broker_name: str = "DEGIRO") -> ParsedStatement:
    path = Path(path)
    source_file = path.name
    rows = _read_rows(path)
    order_groups = _group_by_order_id(rows)
    dividend_fx_rates = _dividend_fx_rates(rows)

    transactions = []
    dividend_components = []
    cash_flows = []
    ignored = []

    for row in rows:
        trade_match = TRADE_RE.match(row.description)
        if trade_match:
            group = order_groups.get(row.order_id, [row])
            quantity = _decimal(trade_match.group("quantity")) or Decimal("0")
            price = _decimal(trade_match.group("price")) or Decimal("0")
            action = "BUY" if trade_match.group("kind") == "Acquisto" else "SELL"
            currency = trade_match.group("currency")
            isin = trade_match.group("isin")
            ticker = _ticker(isin, row.product)
            fx_rate_to_eur = _fx_rate_from_order_group(row, group)
            fees = _fees_from_order_group(fx_rate_to_eur, group)
            source_hash = (
                _combined_hash(source_file, [item.source_hash for item in group])
                if row.order_id
                else row.source_hash
            )

            transactions.append(
                {
                    "trade_date": row.value_date,
                    "broker_name": broker_name,
                    "ticker": ticker,
                    "asset_name": row.product or trade_match.group("name").strip(),
                    "action": action,
                    "quantity": quantity,
                    "price": price,
                    "fees": fees,
                    "currency": currency,
                    "fx_rate_to_eur": fx_rate_to_eur,
                    "notes": _note(
                        source_file,
                        [item.row_number for item in group],
                        row.description,
                    ),
                    "source_hash": source_hash,
                    "source_file": source_file,
                    "source_rows": sorted(item.row_number for item in group),
                }
            )
            continue

        if row.description in {"Dividendo", "Ritenuta sul dividendo"} and row.isin:
            dividend_components.append(row)
            continue

        if row.description == "Deposito flatex" and row.change_amount:
            cash_flows.append(
                {
                    "flow_date": row.value_date,
                    "broker_name": broker_name,
                    "flow_type": "DEPOSIT" if row.change_amount > 0 else "WITHDRAWAL",
                    "amount": abs(row.change_amount),
                    "currency": row.change_currency,
                    "fx_rate_to_eur": Decimal("1"),
                    "notes": _note(source_file, [row.row_number], row.description),
                    "source_hash": row.source_hash,
                    "source_file": source_file,
                    "source_rows": [row.row_number],
                }
            )
            continue

        if row.description.startswith("DEGIRO Costi di connessione") and row.change_amount:
            cash_flows.append(
                {
                    "flow_date": row.value_date,
                    "broker_name": broker_name,
                    "flow_type": "FEE",
                    "amount": abs(row.change_amount),
                    "currency": row.change_currency,
                    "fx_rate_to_eur": Decimal("1"),
                    "notes": _note(source_file, [row.row_number], row.description),
                    "source_hash": row.source_hash,
                    "source_file": source_file,
                    "source_rows": [row.row_number],
                }
            )
            continue

        if row.description == "Flatex Interest Income" and row.change_amount:
            if row.change_amount != 0:
                cash_flows.append(
                    {
                        "flow_date": row.value_date,
                        "broker_name": broker_name,
                        "flow_type": "INTEREST",
                        "amount": abs(row.change_amount),
                        "currency": row.change_currency,
                        "fx_rate_to_eur": Decimal("1"),
                        "notes": _note(source_file, [row.row_number], row.description),
                        "source_hash": row.source_hash,
                        "source_file": source_file,
                        "source_rows": [row.row_number],
                    }
                )
            continue

        if _should_ignore(row):
            ignored.append(_ignored_row(row, "broker bookkeeping or unsupported corporate action"))
            continue

        ignored.append(_ignored_row(row, "unsupported row"))

    dividends = _build_dividends(
        dividend_components,
        dividend_fx_rates,
        source_file,
        broker_name,
    )

    return ParsedStatement(
        source_file=source_file,
        base_currency="EUR",
        transactions=pd.DataFrame(transactions),
        dividends=pd.DataFrame(dividends),
        cash_flows=pd.DataFrame(cash_flows),
        ignored=pd.DataFrame(ignored),
    )


def _build_dividends(
    components: list[DegiroRow],
    dividend_fx_rates: dict[tuple[str, str], Decimal],
    source_file: str,
    broker_name: str,
) -> list[dict]:
    grouped: dict[tuple[str, str, str], list[DegiroRow]] = {}

    for row in components:
        key = (row.value_date, broker_name, _ticker(row.isin, row.product))
        grouped.setdefault(key, []).append(row)

    dividends = []
    for (payment_date, broker, ticker), group in grouped.items():
        currency = next((row.change_currency for row in group if row.change_currency), "EUR")
        gross_amount = sum(
            (
                row.change_amount or Decimal("0")
                for row in group
                if row.description == "Dividendo"
            ),
            Decimal("0"),
        )
        tax_amount = sum(
            (
                row.change_amount or Decimal("0")
                for row in group
                if row.description == "Ritenuta sul dividendo"
            ),
            Decimal("0"),
        )
        net_amount = gross_amount + tax_amount
        fx_rate_to_eur = Decimal("1")
        if currency != "EUR":
            event_date = group[0].date
            fx_rate_to_eur = dividend_fx_rates.get((currency, event_date), Decimal("1"))

        row_numbers = [row.row_number for row in group]
        descriptions = "; ".join(row.description for row in group)
        dividends.append(
            {
                "payment_date": payment_date,
                "broker_name": broker,
                "ticker": ticker,
                "gross_amount": gross_amount,
                "withholding_tax": abs(tax_amount),
                "net_amount": net_amount,
                "currency": currency,
                "fx_rate_to_eur": fx_rate_to_eur,
                "notes": _note(source_file, row_numbers, descriptions),
                "source_hash": _combined_hash(source_file, [row.source_hash for row in group]),
                "source_file": source_file,
                "source_rows": sorted(row_numbers),
            }
        )

    return dividends


def _should_ignore(row: DegiroRow) -> bool:
    if row.description in {
        "Degiro Cash Sweep Transfer",
        "Credito FX",
        "Prelievo FX",
        "Flatex Interest Income",
    }:
        return True

    if row.description.startswith("Trasferisci "):
        return True

    if row.description.lower().startswith("degiro costi di transazione"):
        return True

    if row.description.startswith("FRAZIONAMENTO AZIONARIO"):
        return True

    return False


def _ignored_row(row: DegiroRow, reason: str) -> dict:
    return {
        "row_number": row.row_number,
        "date": row.date,
        "value_date": row.value_date,
        "product": row.product,
        "isin": row.isin,
        "description": row.description,
        "reason": reason,
        "source_hash": row.source_hash,
    }


def main():
    parser = argparse.ArgumentParser(description="Import a DEGIRO account CSV")
    parser.add_argument("path", help="Path to the DEGIRO account CSV")
    parser.add_argument("--broker", default="DEGIRO", help="Broker name to store")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write new rows to the database. Defaults to dry-run.",
    )
    args = parser.parse_args()

    parsed = parse_degiro_account(args.path, broker_name=args.broker)

    try:
        summary = import_statement(
            parsed,
            apply=args.apply,
            source_system=SOURCE_SYSTEM,
        )
    except Exception as exc:
        if args.apply:
            raise

        summary = summarize(parsed)
        summary.update(
            {
                "mode": "dry-run",
                "database": "unavailable",
                "database_error": f"{type(exc).__name__}: {exc}",
            }
        )

    print(json.dumps(summary, indent=2, default=str))

    if not parsed.ignored.empty:
        print("\nIgnored rows:")
        print(parsed.ignored[["row_number", "description", "reason"]].to_string(index=False))

    if not args.apply and summary.get("database") == "unavailable":
        print(
            "\nDry-run parsed the file but could not compare against existing "
            "database rows.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
