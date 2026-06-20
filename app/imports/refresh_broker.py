import argparse
import json
import subprocess
from pathlib import Path
from typing import Callable

from sqlalchemy import text

from app.database.connection import get_engine
from app.imports.import_degiro_account import (
    SOURCE_SYSTEM as DEGIRO_SOURCE_SYSTEM,
    parse_degiro_account,
)
from app.imports.import_ib_statement import (
    SOURCE_SYSTEM as IB_SOURCE_SYSTEM,
    import_statement,
    parse_ib_statement,
)
from app.imports.import_intesa_statements import (
    SOURCE_SYSTEM as INTESA_SOURCE_SYSTEM,
    import_intesa_statements,
    parse_intesa_statements,
)
from app.ops.data_quality import run_all_checks
from app.ops.job_runs import finish_job, start_job


class RefreshError(RuntimeError):
    pass


BROKERS = {
    "IB": {
        "broker_name": "IB",
        "source_system": IB_SOURCE_SYSTEM,
        "parser": parse_ib_statement,
    },
    "DEGIRO": {
        "broker_name": "DEGIRO",
        "source_system": DEGIRO_SOURCE_SYSTEM,
        "parser": parse_degiro_account,
    },
    "INTESA": {
        "broker_name": "INTESA",
        "source_system": INTESA_SOURCE_SYSTEM,
        "parser": parse_intesa_statements,
    },
}


def parse_broker_file(broker: str, path: str | Path):
    config = broker_config(broker)
    parser: Callable = config["parser"]
    if broker.upper() == "INTESA":
        return parser(path)
    return parser(path, broker_name=config["broker_name"])


def import_broker_statement(broker: str, parsed, apply: bool) -> dict:
    config = broker_config(broker)
    if broker.upper() == "INTESA":
        return import_intesa_statements(parsed, apply=apply)
    return import_statement(parsed, apply=apply, source_system=config["source_system"])


def broker_config(broker: str) -> dict:
    broker = broker.upper()
    if broker not in BROKERS:
        valid = ", ".join(sorted(BROKERS))
        raise RefreshError(f"Unsupported broker {broker!r}. Valid brokers: {valid}")
    return BROKERS[broker]


def run_backup() -> str:
    result = subprocess.run(
        ["sh", "app/scripts/backup_database.sh"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RefreshError(result.stderr.strip() or result.stdout.strip())

    return result.stdout.strip()


def delete_broker_rows(broker_name: str, source_system: str) -> dict:
    engine = get_engine()

    with engine.begin() as conn:
        import_records_deleted = conn.execute(
            text("""
                DELETE FROM import_records
                WHERE source_system = :source_system
                   OR (
                        target_table = 'transactions'
                        AND target_id IN (
                            SELECT transaction_id
                            FROM transactions
                            WHERE broker_name = :broker_name
                        )
                   )
                   OR (
                        target_table = 'dividends'
                        AND target_id IN (
                            SELECT dividend_id
                            FROM dividends
                            WHERE broker_name = :broker_name
                        )
                   )
                   OR (
                        target_table = 'cash_flows'
                        AND target_id IN (
                            SELECT cash_flow_id
                            FROM cash_flows
                            WHERE broker_name = :broker_name
                        )
                   )
                   OR (
                        target_table = 'broker_position_valuations'
                        AND target_id IN (
                            SELECT valuation_id
                            FROM broker_position_valuations
                            WHERE broker_name = :broker_name
                        )
                   )
            """),
            {
                "broker_name": broker_name,
                "source_system": source_system,
            },
        ).rowcount

        transactions_deleted = conn.execute(
            text("DELETE FROM transactions WHERE broker_name = :broker_name"),
            {"broker_name": broker_name},
        ).rowcount

        dividends_deleted = conn.execute(
            text("DELETE FROM dividends WHERE broker_name = :broker_name"),
            {"broker_name": broker_name},
        ).rowcount

        cash_flows_deleted = conn.execute(
            text("DELETE FROM cash_flows WHERE broker_name = :broker_name"),
            {"broker_name": broker_name},
        ).rowcount

        valuations_deleted = conn.execute(
            text("DELETE FROM broker_position_valuations WHERE broker_name = :broker_name"),
            {"broker_name": broker_name},
        ).rowcount

    return {
        "import_records": import_records_deleted,
        "transactions": transactions_deleted,
        "dividends": dividends_deleted,
        "cash_flows": cash_flows_deleted,
        "broker_position_valuations": valuations_deleted,
    }


def data_quality_summary() -> dict:
    checks = run_all_checks()
    return {
        name: {
            "status": "ok" if df.empty else "issues",
            "rows": len(df),
        }
        for name, df in checks.items()
    }


def assert_data_quality_ok(summary: dict) -> None:
    failures = {
        name: details["rows"]
        for name, details in summary.items()
        if details["rows"]
    }

    if failures:
        raise RefreshError(f"Data quality issues found after refresh: {failures}")


def refresh_job_name(broker: str) -> str:
    return f"broker_refresh_{broker.upper()}"


def _refresh_rows_processed(report: dict) -> int | None:
    if "apply_summary" in report:
        return int(report["apply_summary"].get("inserted", 0))

    if "pre_refresh_dry_run" in report:
        return int(report["pre_refresh_dry_run"].get("inserted", 0))

    return None


def _finish_refresh_job(
    job_id: int,
    status: str,
    report: dict,
    error: Exception | None = None,
) -> None:
    message = {
        "kind": "broker_refresh",
        "report": report,
    }
    if error is not None:
        message["error"] = str(error)

    finish_job(
        job_id,
        status,
        rows_processed=_refresh_rows_processed(report),
        message=json.dumps(message, default=str),
    )


def refresh_broker(
    broker: str,
    path: str | Path,
    apply: bool = False,
    yes: bool = False,
    skip_backup: bool = False,
) -> dict:
    config = broker_config(broker)
    report = {
        "broker": broker.upper(),
        "broker_name": config["broker_name"],
        "source_system": config["source_system"],
        "requested_file": str(path),
        "mode": "apply" if apply else "dry-run",
    }

    job_id = start_job(refresh_job_name(report["broker"]))

    try:
        parsed = parse_broker_file(broker, path)
        report["source_file"] = parsed.source_file
        report["pre_refresh_dry_run"] = import_broker_statement(broker, parsed, apply=False)

        if not apply:
            report["message"] = (
                "Dry-run only. Re-run with --apply --yes to replace broker rows."
            )
            _finish_refresh_job(job_id, "success", report)
            return report

        if not yes:
            raise RefreshError("--apply requires --yes because this replaces broker rows")

        if not skip_backup:
            report["backup"] = run_backup()
        else:
            report["backup"] = "skipped"

        report["deleted"] = delete_broker_rows(
            broker_name=config["broker_name"],
            source_system=config["source_system"],
        )

        report["apply_summary"] = import_broker_statement(broker, parsed, apply=True)

        report["post_refresh_dry_run"] = import_broker_statement(broker, parsed, apply=False)

        post = report["post_refresh_dry_run"]
        if post["inserted"] != 0 or post["matched_existing"] != 0:
            raise RefreshError(
                "Refresh idempotency check failed: "
                f"inserted={post['inserted']} matched_existing={post['matched_existing']}"
            )

        report["data_quality"] = data_quality_summary()
        assert_data_quality_ok(report["data_quality"])
        _finish_refresh_job(job_id, "success", report)
        return report

    except Exception as exc:
        _finish_refresh_job(job_id, "failed", report, error=exc)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Safely refresh one broker from a full-history broker CSV"
    )
    parser.add_argument("--broker", required=True, choices=sorted(BROKERS))
    parser.add_argument("--file", required=True, help="Full-history broker CSV")
    parser.add_argument("--apply", action="store_true", help="Replace broker rows")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm destructive broker-row replacement when using --apply",
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Skip pre-refresh database backup. Intended only for controlled tests.",
    )
    args = parser.parse_args()

    report = refresh_broker(
        broker=args.broker,
        path=args.file,
        apply=args.apply,
        yes=args.yes,
        skip_backup=args.skip_backup,
    )

    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
