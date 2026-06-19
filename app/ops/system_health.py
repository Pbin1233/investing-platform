from datetime import datetime
from pathlib import Path

import pandas as pd


MIN_BACKUP_SIZE_BYTES = 1024


def latest_backup_info(
    backups_dir: str | Path = "/data/backups",
    min_size_bytes: int = MIN_BACKUP_SIZE_BYTES,
) -> dict:
    backups_dir = Path(backups_dir)

    if not backups_dir.exists():
        return {
            "status": "MISSING",
            "name": None,
            "path": str(backups_dir),
            "size_bytes": 0,
            "modified_at": None,
            "detail": f"Backup directory not found: {backups_dir}",
        }

    files = sorted(
        [
            path
            for path in backups_dir.iterdir()
            if path.is_file() and path.name.endswith(".sql.gz")
        ],
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )

    if not files:
        return {
            "status": "MISSING",
            "name": None,
            "path": str(backups_dir),
            "size_bytes": 0,
            "modified_at": None,
            "detail": f"No .sql.gz backups found in {backups_dir}",
        }

    latest = files[0]
    stat = latest.stat()
    status = "OK" if stat.st_size >= min_size_bytes else "CHECK"
    return {
        "status": status,
        "name": latest.name,
        "path": str(latest),
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime),
        "detail": (
            f"{latest.name} ({stat.st_size} bytes)"
            if status == "OK"
            else f"{latest.name} is only {stat.st_size} bytes"
        ),
    }


def _job_status(latest_jobs: pd.DataFrame, job_name: str) -> tuple[str, str]:
    if latest_jobs.empty or "job_name" not in latest_jobs.columns:
        return "MISSING", f"No {job_name} run found"

    matches = latest_jobs[latest_jobs["job_name"] == job_name]
    if matches.empty:
        return "MISSING", f"No {job_name} run found"

    row = matches.iloc[0]
    status = "OK" if row["status"] == "success" else "CHECK"
    detail = f"{row['status']} at {row['started_at']}"
    if "age_hours" in row and pd.notna(row["age_hours"]):
        detail = f"{detail} ({row['age_hours']} h ago)"

    return status, detail


def build_system_health_rows(
    latest_jobs: pd.DataFrame,
    market_health: pd.DataFrame,
    quality_checks: dict[str, pd.DataFrame],
    backup_info: dict,
) -> pd.DataFrame:
    rows = []

    maintenance_status, maintenance_detail = _job_status(
        latest_jobs,
        "daily_maintenance",
    )
    rows.append(
        {
            "area": "Daily maintenance",
            "status": maintenance_status,
            "detail": maintenance_detail,
        }
    )

    if market_health.empty:
        market_status = "CHECK"
        market_detail = "No active market health rows"
    else:
        issue_count = int((market_health["status"] != "OK").sum())
        market_status = "OK" if issue_count == 0 else "CHECK"
        market_detail = (
            f"{len(market_health)} active securities, {issue_count} issue rows"
        )
    rows.append(
        {
            "area": "Market data",
            "status": market_status,
            "detail": market_detail,
        }
    )

    issue_rows = sum(len(df) for df in quality_checks.values())
    rows.append(
        {
            "area": "Data quality",
            "status": "OK" if issue_rows == 0 else "CHECK",
            "detail": f"{issue_rows} issue rows across {len(quality_checks)} checks",
        }
    )

    for broker_job in ("broker_refresh_DEGIRO", "broker_refresh_IB"):
        status, detail = _job_status(latest_jobs, broker_job)
        rows.append(
            {
                "area": broker_job,
                "status": status,
                "detail": detail,
            }
        )

    rows.append(
        {
            "area": "Latest backup",
            "status": backup_info["status"],
            "detail": backup_info["detail"],
        }
    )

    return pd.DataFrame(rows)
