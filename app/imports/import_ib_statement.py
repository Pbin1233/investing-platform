import argparse
import csv
import hashlib
import json
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from app.database.connection import get_engine


SOURCE_SYSTEM = "IBKR"


@dataclass
class ParsedStatement:
    source_file: str
    base_currency: str
    transactions: pd.DataFrame
    dividends: pd.DataFrame
    cash_flows: pd.DataFrame
    ignored: pd.DataFrame


def _clean(value: str | None) -> str:
    if value is None:
        return ""

    value = value.strip()
    if value == "-":
        return ""

    return value


def _decimal(value: str | None) -> Decimal | None:
    value = _clean(value)
    if not value:
        return None

    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid numeric value: {value}") from exc


def _positive(value: Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0")

    return abs(value)


def _row_hash(source_file: str, row_number: int, row: list[str]) -> str:
    payload = json.dumps(
        {
            "source_file": source_file,
            "row_number": row_number,
            "row": row,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _combined_hash(source_file: str, row_hashes: list[str]) -> str:
    payload = json.dumps(
        {
            "source_file": source_file,
            "component_hashes": sorted(row_hashes),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _note(source_file: str, row_numbers: list[int], description: str) -> str:
    rows = ",".join(str(row_number) for row_number in row_numbers)
    return f"IBKR import {source_file} rows {rows}: {description}"


def _read_statement(path: Path) -> tuple[str, list[dict]]:
    base_currency = "EUR"
    transaction_header = None
    transaction_rows = []
    source_file = path.name

    with path.open(newline="") as handle:
        for row_number, raw_row in enumerate(csv.reader(handle), start=1):
            section = raw_row[0] if len(raw_row) > 0 else ""
            row_type = raw_row[1] if len(raw_row) > 1 else ""

            if section == "Summary" and row_type == "Data":
                if len(raw_row) >= 4 and raw_row[2] == "Base Currency":
                    base_currency = _clean(raw_row[3]) or base_currency

            if section == "Transaction History" and row_type == "Header":
                transaction_header = raw_row[2:]
                continue

            if section != "Transaction History" or row_type != "Data":
                continue

            if transaction_header is None:
                raise ValueError("Transaction History data appeared before its header")

            values = raw_row[2:]
            record = dict(zip(transaction_header, values))
            record["_row_number"] = row_number
            record["_source_hash"] = _row_hash(source_file, row_number, raw_row)
            transaction_rows.append(record)

    return base_currency, transaction_rows


def parse_ib_statement(path: str | Path, broker_name: str = "IBKR") -> ParsedStatement:
    path = Path(path)
    base_currency, rows = _read_statement(path)
    source_file = path.name

    transactions = []
    dividend_components = []
    cash_flows = []
    ignored = []

    for row in rows:
        transaction_type = _clean(row.get("Transaction Type"))
        symbol = _clean(row.get("Symbol")).upper()
        description = _clean(row.get("Description"))
        row_number = int(row["_row_number"])
        source_hash = row["_source_hash"]

        if transaction_type in {"Buy", "Sell"}:
            quantity = _positive(_decimal(row.get("Quantity")))
            price = _positive(_decimal(row.get("Price")))
            gross_amount = _positive(_decimal(row.get("Gross Amount ")))
            commission = _positive(_decimal(row.get("Commission")))
            currency = _clean(row.get("Price Currency")).upper()

            if not symbol or quantity <= 0 or price <= 0:
                raise ValueError(f"Invalid trade row {row_number}")

            native_gross = quantity * price
            fx_rate_to_eur = (
                gross_amount / native_gross
                if native_gross > 0 and gross_amount > 0
                else Decimal("1")
            )
            fees = commission / fx_rate_to_eur if fx_rate_to_eur > 0 else commission

            transactions.append(
                {
                    "trade_date": _clean(row.get("Date")),
                    "broker_name": broker_name,
                    "ticker": symbol,
                    "asset_name": description,
                    "action": "BUY" if transaction_type == "Buy" else "SELL",
                    "quantity": quantity,
                    "price": price,
                    "fees": fees,
                    "currency": currency,
                    "fx_rate_to_eur": fx_rate_to_eur,
                    "notes": _note(source_file, [row_number], description),
                    "source_hash": source_hash,
                    "source_file": source_file,
                    "source_rows": [row_number],
                }
            )
            continue

        if transaction_type in {"Dividend", "Foreign Tax Withholding"} and symbol:
            amount = _decimal(row.get("Net Amount")) or Decimal("0")
            dividend_components.append(
                {
                    "payment_date": _clean(row.get("Date")),
                    "broker_name": broker_name,
                    "ticker": symbol,
                    "transaction_type": transaction_type,
                    "amount": amount,
                    "description": description,
                    "source_hash": source_hash,
                    "source_file": source_file,
                    "source_rows": [row_number],
                }
            )
            continue

        if transaction_type == "Deposit":
            amount = _decimal(row.get("Net Amount")) or Decimal("0")
            flow_type = "DEPOSIT" if amount >= 0 else "WITHDRAWAL"
            cash_flows.append(
                {
                    "flow_date": _clean(row.get("Date")),
                    "broker_name": broker_name,
                    "flow_type": flow_type,
                    "amount": abs(amount),
                    "currency": base_currency,
                    "fx_rate_to_eur": Decimal("1"),
                    "notes": _note(source_file, [row_number], description),
                    "source_hash": source_hash,
                    "source_file": source_file,
                    "source_rows": [row_number],
                }
            )
            continue

        ignored.append(
            {
                "row_number": row_number,
                "transaction_type": transaction_type,
                "symbol": symbol,
                "description": description,
                "reason": "unsupported transaction type",
                "source_hash": source_hash,
            }
        )

    dividends = _build_dividends(dividend_components, source_file, base_currency)

    return ParsedStatement(
        source_file=source_file,
        base_currency=base_currency,
        transactions=pd.DataFrame(transactions),
        dividends=pd.DataFrame(dividends),
        cash_flows=pd.DataFrame(cash_flows),
        ignored=pd.DataFrame(ignored),
    )


def _build_dividends(
    components: list[dict],
    source_file: str,
    base_currency: str,
) -> list[dict]:
    grouped: dict[tuple[str, str, str], list[dict]] = {}

    for component in components:
        key = (
            component["payment_date"],
            component["broker_name"],
            component["ticker"],
        )
        grouped.setdefault(key, []).append(component)

    dividends = []
    for (payment_date, broker_name, ticker), group in grouped.items():
        dividend_amount = sum(
            (
                item["amount"]
                for item in group
                if item["transaction_type"] == "Dividend"
            ),
            Decimal("0"),
        )
        tax_amount = sum(
            (
                item["amount"]
                for item in group
                if item["transaction_type"] == "Foreign Tax Withholding"
            ),
            Decimal("0"),
        )
        row_numbers = [
            row_number
            for item in group
            for row_number in item["source_rows"]
        ]
        descriptions = "; ".join(item["description"] for item in group)
        source_hashes = [item["source_hash"] for item in group]

        dividends.append(
            {
                "payment_date": payment_date,
                "broker_name": broker_name,
                "ticker": ticker,
                "gross_amount": dividend_amount,
                "withholding_tax": -tax_amount,
                "net_amount": dividend_amount + tax_amount,
                "currency": base_currency,
                "fx_rate_to_eur": Decimal("1"),
                "notes": _note(source_file, sorted(row_numbers), descriptions),
                "source_hash": _combined_hash(source_file, source_hashes),
                "source_file": source_file,
                "source_rows": sorted(row_numbers),
            }
        )

    return dividends


def _existing_source_hashes(conn, hashes: list[str]) -> set[str]:
    if not hashes:
        return set()

    rows = conn.execute(
        text("""
            SELECT source_hash
            FROM import_records
            WHERE source_hash = ANY(:hashes)
        """),
        {"hashes": hashes},
    )
    return {row[0] for row in rows}


def _find_existing_transaction(conn, row: dict) -> int | None:
    return conn.execute(
        text("""
            SELECT transaction_id
            FROM transactions
            WHERE trade_date = :trade_date
              AND broker_name = :broker_name
              AND ticker = :ticker
              AND action = :action
              AND quantity = :quantity
              AND price = :price
              AND fees = :fees
              AND currency = :currency
              AND fx_rate_to_eur = :fx_rate_to_eur
            ORDER BY transaction_id
            LIMIT 1
        """),
        row,
    ).scalar()


def _find_existing_dividend(conn, row: dict) -> int | None:
    return conn.execute(
        text("""
            SELECT dividend_id
            FROM dividends
            WHERE payment_date = :payment_date
              AND broker_name = :broker_name
              AND ticker = :ticker
              AND gross_amount = :gross_amount
              AND withholding_tax = :withholding_tax
              AND net_amount = :net_amount
              AND currency = :currency
              AND fx_rate_to_eur = :fx_rate_to_eur
            ORDER BY dividend_id
            LIMIT 1
        """),
        row,
    ).scalar()


def _find_existing_cash_flow(conn, row: dict) -> int | None:
    return conn.execute(
        text("""
            SELECT cash_flow_id
            FROM cash_flows
            WHERE flow_date = :flow_date
              AND broker_name = :broker_name
              AND flow_type = :flow_type
              AND amount = :amount
              AND currency = :currency
              AND fx_rate_to_eur = :fx_rate_to_eur
              AND notes = :notes
            ORDER BY cash_flow_id
            LIMIT 1
        """),
        row,
    ).scalar()


def _insert_import_record(conn, source_system, source_file, source_hash, target_table, target_id):
    conn.execute(
        text("""
            INSERT INTO import_records (
                source_system,
                source_file,
                source_hash,
                target_table,
                target_id
            )
            VALUES (
                :source_system,
                :source_file,
                :source_hash,
                :target_table,
                :target_id
            )
            ON CONFLICT (source_hash) DO NOTHING
        """),
        {
            "source_system": source_system,
            "source_file": source_file,
            "source_hash": source_hash,
            "target_table": target_table,
            "target_id": target_id,
        },
    )


def _insert_transaction(conn, row: dict) -> int:
    return conn.execute(
        text("""
            INSERT INTO transactions (
                trade_date,
                broker_name,
                ticker,
                asset_name,
                action,
                quantity,
                price,
                fees,
                currency,
                fx_rate_to_eur,
                notes
            )
            VALUES (
                :trade_date,
                :broker_name,
                :ticker,
                :asset_name,
                :action,
                :quantity,
                :price,
                :fees,
                :currency,
                :fx_rate_to_eur,
                :notes
            )
            RETURNING transaction_id
        """),
        row,
    ).scalar_one()


def _insert_dividend(conn, row: dict) -> int:
    return conn.execute(
        text("""
            INSERT INTO dividends (
                payment_date,
                broker_name,
                ticker,
                gross_amount,
                withholding_tax,
                net_amount,
                currency,
                fx_rate_to_eur,
                notes
            )
            VALUES (
                :payment_date,
                :broker_name,
                :ticker,
                :gross_amount,
                :withholding_tax,
                :net_amount,
                :currency,
                :fx_rate_to_eur,
                :notes
            )
            RETURNING dividend_id
        """),
        row,
    ).scalar_one()


def _insert_cash_flow(conn, row: dict) -> int:
    return conn.execute(
        text("""
            INSERT INTO cash_flows (
                flow_date,
                broker_name,
                flow_type,
                amount,
                currency,
                fx_rate_to_eur,
                notes
            )
            VALUES (
                :flow_date,
                :broker_name,
                :flow_type,
                :amount,
                :currency,
                :fx_rate_to_eur,
                :notes
            )
            RETURNING cash_flow_id
        """),
        row,
    ).scalar_one()


def _public_rows(df: pd.DataFrame, columns: list[str]) -> list[dict]:
    if df.empty:
        return []

    return df[columns].to_dict("records")


def summarize(parsed: ParsedStatement) -> dict:
    return {
        "source_file": parsed.source_file,
        "base_currency": parsed.base_currency,
        "transactions": len(parsed.transactions),
        "dividends": len(parsed.dividends),
        "cash_flows": len(parsed.cash_flows),
        "ignored": len(parsed.ignored),
    }


def import_statement(
    parsed: ParsedStatement,
    apply: bool = False,
    source_system: str = SOURCE_SYSTEM,
) -> dict:
    engine = get_engine()
    summary = summarize(parsed)
    summary.update(
        {
            "already_imported": 0,
            "matched_existing": 0,
            "inserted": 0,
            "mode": "apply" if apply else "dry-run",
        }
    )

    frames = [
        (
            "transactions",
            parsed.transactions,
            [
                "trade_date",
                "broker_name",
                "ticker",
                "asset_name",
                "action",
                "quantity",
                "price",
                "fees",
                "currency",
                "fx_rate_to_eur",
                "notes",
            ],
            _find_existing_transaction,
            _insert_transaction,
        ),
        (
            "dividends",
            parsed.dividends,
            [
                "payment_date",
                "broker_name",
                "ticker",
                "gross_amount",
                "withholding_tax",
                "net_amount",
                "currency",
                "fx_rate_to_eur",
                "notes",
            ],
            _find_existing_dividend,
            _insert_dividend,
        ),
        (
            "cash_flows",
            parsed.cash_flows,
            [
                "flow_date",
                "broker_name",
                "flow_type",
                "amount",
                "currency",
                "fx_rate_to_eur",
                "notes",
            ],
            _find_existing_cash_flow,
            _insert_cash_flow,
        ),
    ]

    all_hashes = []
    for _, frame, _, _, _ in frames:
        if not frame.empty:
            all_hashes.extend(frame["source_hash"].tolist())

    with engine.begin() as conn:
        existing_hashes = _existing_source_hashes(conn, all_hashes)

        if apply:
            broker_names = set()
            for _, frame, _, _, _ in frames:
                if not frame.empty and "broker_name" in frame:
                    broker_names.update(frame["broker_name"].dropna().unique())

            for broker_name in sorted(broker_names):
                conn.execute(
                    text("""
                        INSERT INTO brokers (broker_name, base_currency)
                        VALUES (:broker_name, :base_currency)
                        ON CONFLICT (broker_name) DO NOTHING
                    """),
                    {
                        "broker_name": broker_name,
                        "base_currency": parsed.base_currency,
                    },
                )

        for table_name, frame, public_columns, find_existing, insert_row in frames:
            for row in _public_rows(frame, public_columns + ["source_hash", "source_file"]):
                source_hash = row.pop("source_hash")
                source_file = row.pop("source_file")

                if source_hash in existing_hashes:
                    summary["already_imported"] += 1
                    continue

                existing_id = find_existing(conn, row)
                if existing_id is not None:
                    summary["matched_existing"] += 1
                    if apply:
                        _insert_import_record(
                            conn,
                            source_system,
                            source_file,
                            source_hash,
                            table_name,
                            existing_id,
                        )
                    continue

                summary["inserted"] += 1
                if apply:
                    target_id = insert_row(conn, row)
                    _insert_import_record(
                        conn,
                        source_system,
                        source_file,
                        source_hash,
                        table_name,
                        target_id,
                    )

    return summary


def main():
    parser = argparse.ArgumentParser(description="Import an IBKR statement CSV")
    parser.add_argument("path", help="Path to the IBKR statement CSV")
    parser.add_argument("--broker", default="IBKR", help="Broker name to store")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write new rows to the database. Defaults to dry-run.",
    )
    args = parser.parse_args()

    parsed = parse_ib_statement(args.path, broker_name=args.broker)

    try:
        summary = import_statement(parsed, apply=args.apply)
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
        print(parsed.ignored[["row_number", "transaction_type", "symbol", "reason"]].to_string(index=False))

    if not args.apply and summary.get("database") == "unavailable":
        print(
            "\nDry-run parsed the file but could not compare against existing "
            "database rows.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
