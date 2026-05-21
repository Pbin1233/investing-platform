import argparse
import json

from sqlalchemy import text

from app.database.connection import get_engine


def maybe_pretty_json(value):
    if not value:
        return ""

    try:
        return json.dumps(json.loads(value), indent=2)
    except json.JSONDecodeError:
        return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--job-name", type=str, default=None)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    query = """
        SELECT id, job_name, status, rows_processed, started_at, completed_at, message
        FROM job_runs
    """

    params = {"limit": args.limit}

    if args.job_name:
        query += " WHERE job_name = :job_name"
        params["job_name"] = args.job_name

    query += " ORDER BY id DESC LIMIT :limit"

    with get_engine().connect() as conn:
        rows = conn.execute(text(query), params).fetchall()

    for row in rows:
        print("=" * 80)
        print(f"id: {row.id}")
        print(f"job_name: {row.job_name}")
        print(f"status: {row.status}")
        print(f"rows_processed: {row.rows_processed}")
        print(f"started_at: {row.started_at}")
        print(f"completed_at: {row.completed_at}")

        message = maybe_pretty_json(row.message) if args.pretty else row.message
        print(f"message:\n{message}")


if __name__ == "__main__":
    main()
