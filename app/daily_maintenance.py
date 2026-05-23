import json
import subprocess
from datetime import datetime, timezone

from app.ops.job_runs import start_job, finish_job
from app.market_data.update_prices import main as update_prices
from app.market_data.update_daily_prices import update_daily_prices
from app.snapshots.snapshot_portfolio import snapshot_portfolio


def run_stage(stage_name, func):
    started_at = datetime.now(timezone.utc)

    try:
        result = func()
        completed_at = datetime.now(timezone.utc)

        return {
            "stage": stage_name,
            "status": "success",
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "message": str(result) if result is not None else None,
        }

    except Exception as exc:
        completed_at = datetime.now(timezone.utc)

        return {
            "stage": stage_name,
            "status": "failed",
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "message": str(exc),
        }


def run_backup():
    result = subprocess.run(
        ["sh", "app/scripts/backup_database.sh"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)

    return result.stdout.strip()


def main():
    job_id = start_job("daily_maintenance")
    stages = []

    pipeline = [
        ("update_prices", update_prices),
        ("update_daily_prices", update_daily_prices),
        ("snapshot_portfolio", snapshot_portfolio),
        ("backup_database", run_backup),
    ]

    for stage_name, func in pipeline:
        print(f"Running stage: {stage_name}")
        result = run_stage(stage_name, func)
        stages.append(result)

        if result["status"] == "failed":
            message = json.dumps({"stages": stages}, default=str)
            finish_job(
                job_id,
                "failed",
                rows_processed=None,
                message=message,
            )
            raise RuntimeError(f"Daily maintenance failed at {stage_name}")

    message = json.dumps({"stages": stages}, default=str)

    finish_job(
        job_id,
        "success",
        rows_processed=None,
        message=message,
    )

    print("Daily maintenance complete.")


if __name__ == "__main__":
    main()
