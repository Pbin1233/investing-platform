from pathlib import Path
from sqlalchemy import text

from app.database.connection import get_engine

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def main():
    engine = get_engine()
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    with engine.begin() as conn:

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_name TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))

        applied = {
            row[0]
            for row in conn.execute(
                text("SELECT migration_name FROM schema_migrations")
            )
        }

        for path in migration_files:
            migration_name = path.name

            if migration_name in applied:
                print(f"Skipping {migration_name}")
                continue

            print(f"Applying {migration_name}")

            conn.execute(text(path.read_text()))

            conn.execute(
                text("""
                    INSERT INTO schema_migrations (migration_name)
                    VALUES (:migration_name)
                """),
                {"migration_name": migration_name},
            )

    print("Migrations complete.")


if __name__ == "__main__":
    main()
