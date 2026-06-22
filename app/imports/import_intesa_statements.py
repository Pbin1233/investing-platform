import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from app.database.connection import get_engine


SOURCE_SYSTEM = "INTESA"
BROKER_NAME = "INTESA"
BTP_TICKER = "IT0005532715"
BTP_NAME = "BTP Italia 14 Mar 2028 2.00%"
AMOUNT_RE = re.compile(
    r"(?<![\d.])([+-]?\s*(?:\d{1,3}(?:[.\s]\s*\d{3})+|\d+),\s*\d{2})\s*(?:€|EUR)"
)


@dataclass
class ParsedIntesaStatements:
    source_file: str
    transactions: pd.DataFrame
    dividends: pd.DataFrame
    valuations: pd.DataFrame
    ignored: pd.DataFrame


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _row_hash(*parts) -> str:
    payload = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _decimal(value: str | int | float | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value

    text_value = str(value).strip().replace("\x19", ".")
    text_value = re.sub(r"\s+", "", text_value)
    text_value = text_value.replace(".", "").replace(",", ".")
    text_value = text_value.replace("+", "")
    return Decimal(text_value)


def _date(value: str) -> date:
    day, month, year = re.findall(r"\d+", value)[:3]
    return date(int(year), int(month), int(day))


def _text_from_pdf(path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"pdftotext failed for {path}")
    return result.stdout


def _iter_pdf_documents(path: str | Path):
    path = Path(path)
    if path.is_dir():
        for child in sorted(path.iterdir()):
            yield from _iter_pdf_documents(child)
        return

    if path.suffix.lower() == ".pdf":
        data = path.read_bytes()
        yield path.name, data
        return

    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            for info in sorted(zf.infolist(), key=lambda item: item.filename):
                if not info.filename.lower().endswith(".pdf"):
                    continue
                yield f"{path.name}:{info.filename}", zf.read(info)


def _clean_text(text_value: str) -> str:
    return re.sub(r"\s+", " ", text_value.replace("\x19", ".")).strip()


def _amount_after(label: str, text_value: str, *, last: bool = False) -> Decimal | None:
    index = text_value.find(label)
    if index < 0:
        return None

    snippet = text_value[index : index + 260].replace("\x19", ".")
    matches = AMOUNT_RE.findall(snippet)
    if not matches:
        return None
    return _decimal(matches[-1] if last else matches[0])


def _line_amount_after(label: str, text_value: str) -> Decimal | None:
    for line in text_value.replace("\x19", ".").splitlines():
        if label not in line:
            continue
        matches = AMOUNT_RE.findall(line[line.find(label) + len(label) :])
        if matches:
            return _decimal(matches[-1])
    return None


def _statement_date(text_value: str) -> date | None:
    match = re.search(r"AL\s+(\d{2}\.\d{2}\.\d{4})", _clean_text(text_value))
    return _date(match.group(1)) if match else None


def _parse_valuation(source_file: str, source_hash: str, text_value: str) -> dict | None:
    if "RENDICONTO TITOLI" not in text_value or BTP_TICKER not in text_value:
        return None

    valuation_date = _statement_date(text_value)
    market_value = _amount_after("Controvalore titoli e fondi", text_value)
    if valuation_date is None or market_value is None:
        return None

    return {
        "broker_name": BROKER_NAME,
        "source_system": SOURCE_SYSTEM,
        "source_file": source_file,
        "valuation_date": valuation_date,
        "ticker": BTP_TICKER,
        "asset_name": BTP_NAME,
        "quantity": Decimal("25000"),
        "market_value_eur": market_value,
        "currency": "EUR",
        "source_hash": _row_hash(source_hash, "valuation", valuation_date, BTP_TICKER, market_value),
    }


def _parse_purchase(source_file: str, source_hash: str, text_value: str) -> dict | None:
    if BTP_TICKER not in text_value or "ACQUISTO" not in text_value.upper():
        return None

    clean = _clean_text(text_value)
    trade_date = None
    settlement = re.search(r"Data di regolamento\s*:\s*(\d{2}/\d{2}/\d{4})", clean)
    if settlement:
        trade_date = _date(settlement.group(1).replace("/", "."))

    nominal = re.search(r"Valore nominale\s*:\s*([0-9\.\s,]+)", clean)
    price = re.search(r"PREZZO\s+([0-9\.\s,]+)\s+EUR", clean)
    if trade_date is None or nominal is None or price is None:
        return None

    quantity = _decimal(nominal.group(1))
    trade_price = _decimal(price.group(1)) / Decimal("100")
    return {
        "trade_date": trade_date,
        "broker_name": BROKER_NAME,
        "ticker": BTP_TICKER,
        "asset_name": BTP_NAME,
        "action": "BUY",
        "quantity": quantity,
        "price": trade_price,
        "fees": Decimal("0"),
        "currency": "EUR",
        "fx_rate_to_eur": Decimal("1"),
        "notes": f"Intesa purchase confirmation: {source_file}",
        "source_file": source_file,
        "source_hash": _row_hash(source_hash, "transaction", trade_date, BTP_TICKER, quantity, trade_price),
    }


def _parse_coupon(source_file: str, source_hash: str, text_value: str) -> dict | None:
    if "CEDOLE, DIVIDENDI, PROVENTI" not in text_value:
        return None

    clean = _clean_text(text_value)
    if BTP_TICKER not in clean and "BTPIT 14MZ28" not in clean:
        return None

    event_date = re.search(r"eventi amministrativi del\s+(\d{2}\.\d{2}\.\d{4})", clean)
    if not event_date:
        return None
    payment_date = _date(event_date.group(1))

    net_amount = _line_amount_after("Totale interessi regolati", text_value)
    if net_amount is None:
        net_amount = _line_amount_after("Interessi da regolare in conto", text_value)
    if net_amount is None:
        return None

    withholding_tax = Decimal("0")
    gross_amount = net_amount

    return {
        "payment_date": payment_date,
        "broker_name": BROKER_NAME,
        "ticker": BTP_TICKER,
        "gross_amount": gross_amount,
        "withholding_tax": withholding_tax,
        "net_amount": net_amount,
        "currency": "EUR",
        "fx_rate_to_eur": Decimal("1"),
        "notes": f"Intesa BTP coupon: {source_file}",
        "source_file": source_file,
        "source_hash": _row_hash(source_hash, "coupon", payment_date, BTP_TICKER, gross_amount, net_amount),
    }


def parse_intesa_statements(path: str | Path) -> ParsedIntesaStatements:
    transactions = []
    dividends = []
    valuations = []
    ignored = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        for source_file, data in _iter_pdf_documents(path):
            source_hash = _sha256_bytes(data)
            pdf_path = tmpdir_path / f"{source_hash}.pdf"
            pdf_path.write_bytes(data)
            text_value = _text_from_pdf(pdf_path)

            parsed_any = False
            purchase = _parse_purchase(source_file, source_hash, text_value)
            if purchase:
                transactions.append(purchase)
                parsed_any = True

            coupon = _parse_coupon(source_file, source_hash, text_value)
            if coupon:
                dividends.append(coupon)
                parsed_any = True

            valuation = _parse_valuation(source_file, source_hash, text_value)
            if valuation:
                valuations.append(valuation)
                parsed_any = True

            if not parsed_any:
                ignored.append({"source_file": source_file, "reason": "unsupported_intesa_pdf"})

    return ParsedIntesaStatements(
        source_file=str(path),
        transactions=pd.DataFrame(transactions),
        dividends=pd.DataFrame(dividends),
        valuations=pd.DataFrame(valuations),
        ignored=pd.DataFrame(ignored),
    )


def _existing_source_hashes(conn, hashes: list[str]) -> set[str]:
    if not hashes:
        return set()
    rows = conn.execute(
        text("SELECT source_hash FROM import_records WHERE source_hash = ANY(:hashes)"),
        {"hashes": hashes},
    )
    return {row[0] for row in rows}


def _insert_import_record(conn, source_file, source_hash, target_table, target_id):
    conn.execute(
        text("""
            INSERT INTO import_records (
                source_system, source_file, source_hash, target_table, target_id
            )
            VALUES (:source_system, :source_file, :source_hash, :target_table, :target_id)
            ON CONFLICT (source_hash) DO NOTHING
        """),
        {
            "source_system": SOURCE_SYSTEM,
            "source_file": source_file,
            "source_hash": source_hash,
            "target_table": target_table,
            "target_id": target_id,
        },
    )


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


def _find_existing_valuation(conn, row: dict) -> int | None:
    return conn.execute(
        text("""
            SELECT valuation_id
            FROM broker_position_valuations
            WHERE broker_name = :broker_name
              AND source_system = :source_system
              AND valuation_date = :valuation_date
              AND ticker = :ticker
              AND quantity = :quantity
              AND market_value_eur = :market_value_eur
              AND currency = :currency
            ORDER BY valuation_id
            LIMIT 1
        """),
        row,
    ).scalar()


def _insert_transaction(conn, row: dict) -> int:
    return conn.execute(
        text("""
            INSERT INTO transactions (
                trade_date, broker_name, ticker, asset_name, action, quantity, price,
                fees, currency, fx_rate_to_eur, notes
            )
            VALUES (
                :trade_date, :broker_name, :ticker, :asset_name, :action, :quantity,
                :price, :fees, :currency, :fx_rate_to_eur, :notes
            )
            RETURNING transaction_id
        """),
        row,
    ).scalar_one()


def _insert_dividend(conn, row: dict) -> int:
    return conn.execute(
        text("""
            INSERT INTO dividends (
                payment_date, broker_name, ticker, gross_amount, withholding_tax,
                net_amount, currency, fx_rate_to_eur, notes
            )
            VALUES (
                :payment_date, :broker_name, :ticker, :gross_amount, :withholding_tax,
                :net_amount, :currency, :fx_rate_to_eur, :notes
            )
            RETURNING dividend_id
        """),
        row,
    ).scalar_one()


def _insert_valuation(conn, row: dict) -> int:
    return conn.execute(
        text("""
            INSERT INTO broker_position_valuations (
                broker_name, source_system, source_file, valuation_date, ticker,
                asset_name, quantity, market_value_eur, currency
            )
            VALUES (
                :broker_name, :source_system, :source_file, :valuation_date, :ticker,
                :asset_name, :quantity, :market_value_eur, :currency
            )
            RETURNING valuation_id
        """),
        row,
    ).scalar_one()


def summarize(parsed: ParsedIntesaStatements) -> dict:
    return {
        "source_file": parsed.source_file,
        "transactions": len(parsed.transactions),
        "dividends": len(parsed.dividends),
        "valuations": len(parsed.valuations),
        "ignored": len(parsed.ignored),
    }


def _public_rows(df: pd.DataFrame, columns: list[str]) -> list[dict]:
    if df.empty:
        return []
    return df[columns].to_dict("records")


def import_intesa_statements(parsed: ParsedIntesaStatements, apply: bool = False) -> dict:
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
                "trade_date", "broker_name", "ticker", "asset_name", "action",
                "quantity", "price", "fees", "currency", "fx_rate_to_eur", "notes",
                "source_file",
            ],
            _find_existing_transaction,
            _insert_transaction,
        ),
        (
            "dividends",
            parsed.dividends,
            [
                "payment_date", "broker_name", "ticker", "gross_amount",
                "withholding_tax", "net_amount", "currency", "fx_rate_to_eur", "notes",
                "source_file",
            ],
            _find_existing_dividend,
            _insert_dividend,
        ),
        (
            "broker_position_valuations",
            parsed.valuations,
            [
                "broker_name", "source_system", "source_file", "valuation_date",
                "ticker", "asset_name", "quantity", "market_value_eur", "currency",
            ],
            _find_existing_valuation,
            _insert_valuation,
        ),
    ]

    all_hashes = []
    for _, frame, _, _, _ in frames:
        if not frame.empty:
            all_hashes.extend(frame["source_hash"].tolist())

    with engine.begin() as conn:
        existing_hashes = _existing_source_hashes(conn, all_hashes)
        if apply:
            conn.execute(
                text("""
                    INSERT INTO brokers (broker_name, base_currency)
                    VALUES (:broker_name, 'EUR')
                    ON CONFLICT (broker_name) DO NOTHING
                """),
                {"broker_name": BROKER_NAME},
            )
            conn.execute(
                text("""
                    INSERT INTO securities (
                        ticker, asset_name, price_symbol, quote_currency, exchange, country, active
                    )
                    VALUES (
                        :ticker, :asset_name, :price_symbol, 'EUR', 'MOT', 'ITA', TRUE
                    )
                    ON CONFLICT (ticker) DO UPDATE
                    SET asset_name = EXCLUDED.asset_name,
                        price_symbol = EXCLUDED.price_symbol,
                        quote_currency = EXCLUDED.quote_currency,
                        exchange = EXCLUDED.exchange,
                        country = EXCLUDED.country,
                        active = TRUE
                """),
                {
                    "ticker": BTP_TICKER,
                    "asset_name": BTP_NAME,
                    "price_symbol": BTP_TICKER,
                },
            )

        for table_name, frame, public_columns, find_existing, insert_row in frames:
            for row in _public_rows(frame, public_columns + ["source_hash"]):
                source_hash = row.pop("source_hash")
                source_file = row.get("source_file")

                if source_hash in existing_hashes:
                    summary["already_imported"] += 1
                    continue

                existing_id = find_existing(conn, row)
                if existing_id is not None:
                    summary["matched_existing"] += 1
                    if apply:
                        _insert_import_record(conn, source_file, source_hash, table_name, existing_id)
                    continue

                summary["inserted"] += 1
                if apply:
                    target_id = insert_row(conn, row)
                    _insert_import_record(conn, source_file, source_hash, table_name, target_id)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Intesa investment PDFs or ZIPs")
    parser.add_argument("path", help="Folder, PDF, or ZIP exported from Intesa")
    parser.add_argument("--apply", action="store_true", help="Write rows to the database")
    args = parser.parse_args()

    parsed = parse_intesa_statements(args.path)
    summary = import_intesa_statements(parsed, apply=args.apply)
    print(json.dumps(summary, indent=2, default=str))

    if not parsed.ignored.empty:
        print("\nIgnored documents:")
        print(parsed.ignored.to_string(index=False))


if __name__ == "__main__":
    main()
