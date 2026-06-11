import argparse
import json
from pathlib import Path

from app.imports.refresh_broker import BROKERS, refresh_broker


DEFAULT_IMPORT_ROOT = Path("/data/activity imports")
BROKER_IMPORT_DIRS = {
    "IB": "ib",
    "DEGIRO": "degiro",
}


def find_latest_csv(import_root: str | Path, broker: str) -> Path:
    broker = broker.upper()
    if broker not in BROKER_IMPORT_DIRS:
        valid = ", ".join(sorted(BROKER_IMPORT_DIRS))
        raise ValueError(f"Unsupported broker {broker!r}. Valid brokers: {valid}")

    broker_dir = Path(import_root) / BROKER_IMPORT_DIRS[broker]
    if not broker_dir.exists():
        raise FileNotFoundError(f"No CSV files found in {broker_dir}")

    candidates = [
        path
        for path in broker_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".csv"
    ]

    if not candidates:
        raise FileNotFoundError(f"No CSV files found in {broker_dir}")

    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def refresh_all_brokers(
    import_root: str | Path = DEFAULT_IMPORT_ROOT,
    brokers: list[str] | None = None,
    apply: bool = False,
    yes: bool = False,
    skip_backup: bool = False,
) -> dict:
    if brokers is None:
        brokers = sorted(BROKERS)

    reports = []

    for broker in brokers:
        broker = broker.upper()
        broker_report = {
            "broker": broker,
            "status": "started",
        }

        try:
            path = find_latest_csv(import_root, broker)
            broker_report["file"] = str(path)
            broker_report["refresh"] = refresh_broker(
                broker=broker,
                path=path,
                apply=apply,
                yes=yes,
                skip_backup=skip_backup,
            )
            broker_report["status"] = "success"
        except Exception as exc:
            broker_report["status"] = "failed"
            broker_report["error"] = str(exc)

        reports.append(broker_report)

    failures = [report for report in reports if report["status"] != "success"]
    return {
        "mode": "apply" if apply else "dry-run",
        "import_root": str(import_root),
        "brokers": reports,
        "status": "failed" if failures else "success",
    }


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Refresh all configured brokers from the latest CSV in each import folder"
    )
    parser.add_argument(
        "--import-root",
        default=str(DEFAULT_IMPORT_ROOT),
        help="Root folder containing broker subfolders, default: /data/activity imports",
    )
    parser.add_argument(
        "--broker",
        dest="brokers",
        action="append",
        choices=sorted(BROKERS),
        help="Broker to refresh. Can be repeated. Defaults to all brokers.",
    )
    parser.add_argument("--apply", action="store_true", help="Replace broker rows")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm destructive broker-row replacement when using --apply",
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Skip per-broker database backups. Intended only for controlled tests.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = refresh_all_brokers(
        import_root=args.import_root,
        brokers=args.brokers,
        apply=args.apply,
        yes=args.yes,
        skip_backup=args.skip_backup,
    )

    print(json.dumps(report, indent=2, default=str))

    if report["status"] != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
