import subprocess

from app.ops.job_runs import start_job, finish_job
from app.market_data.update_prices import main as update_prices
from app.snapshots.snapshot_portfolio import snapshot_portfolio


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

    try:
        print("Updating market prices...")
        update_prices()

        print("Creating portfolio snapshot...")
        snapshot_portfolio()

        print("Running database backup...")
        backup_message = run_backup()

        finish_job(
            job_id,
            "success",
            message=backup_message,
        )

        print("Daily maintenance complete.")

    except Exception as exc:
        finish_job(
            job_id,
            "failed",
            message=str(exc),
        )
        raise


if __name__ == "__main__":
    main()
