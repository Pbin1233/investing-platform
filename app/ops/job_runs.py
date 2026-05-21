from sqlalchemy import text

from app.database.connection import get_engine


def start_job(job_name: str) -> int:
    engine = get_engine()

    with engine.begin() as conn:
        job_id = conn.execute(
            text("""
                INSERT INTO job_runs (job_name, status)
                VALUES (:job_name, 'started')
                RETURNING id
            """),
            {"job_name": job_name},
        ).scalar_one()

    return int(job_id)


def finish_job(
    job_id: int,
    status: str,
    rows_processed: int | None = None,
    message: str | None = None,
) -> None:

    if status not in {"success", "failed"}:
        raise ValueError("status must be 'success' or 'failed'")

    engine = get_engine()

    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE job_runs
                SET completed_at = NOW(),
                    status = :status,
                    rows_processed = :rows_processed,
                    message = :message
                WHERE id = :job_id
            """),
            {
                "job_id": job_id,
                "status": status,
                "rows_processed": rows_processed,
                "message": message,
            },
        )
