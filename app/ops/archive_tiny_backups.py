import argparse
import json
from pathlib import Path

from app.ops.system_health import MIN_BACKUP_SIZE_BYTES


DEFAULT_BACKUPS_DIR = Path("/data/backups")
DEFAULT_ARCHIVE_DIR_NAME = "archive"


def find_tiny_backups(
    backups_dir: str | Path = DEFAULT_BACKUPS_DIR,
    min_size_bytes: int = MIN_BACKUP_SIZE_BYTES,
) -> list[Path]:
    backups_dir = Path(backups_dir)

    if not backups_dir.exists():
        return []

    return sorted(
        [
            path
            for path in backups_dir.iterdir()
            if path.is_file()
            and path.name.endswith(".sql.gz")
            and path.stat().st_size < min_size_bytes
        ],
        key=lambda path: path.name,
    )


def archive_tiny_backups(
    backups_dir: str | Path = DEFAULT_BACKUPS_DIR,
    archive_dir: str | Path | None = None,
    min_size_bytes: int = MIN_BACKUP_SIZE_BYTES,
    apply: bool = False,
) -> dict:
    backups_dir = Path(backups_dir)
    if archive_dir is None:
        archive_dir = backups_dir / DEFAULT_ARCHIVE_DIR_NAME
    else:
        archive_dir = Path(archive_dir)

    tiny_backups = find_tiny_backups(backups_dir, min_size_bytes=min_size_bytes)
    rows = []

    if apply and tiny_backups:
        archive_dir.mkdir(parents=True, exist_ok=True)

    for source in tiny_backups:
        destination = archive_dir / source.name
        row = {
            "source": str(source),
            "destination": str(destination),
            "size_bytes": source.stat().st_size,
            "status": "would_archive",
        }

        if apply:
            source.replace(destination)
            row["status"] = "archived"

        rows.append(row)

    return {
        "mode": "apply" if apply else "dry-run",
        "backups_dir": str(backups_dir),
        "archive_dir": str(archive_dir),
        "min_size_bytes": min_size_bytes,
        "count": len(rows),
        "backups": rows,
    }


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Archive suspiciously tiny PostgreSQL backup files"
    )
    parser.add_argument(
        "--backups-dir",
        default=str(DEFAULT_BACKUPS_DIR),
        help="Backup folder to scan, default: /data/backups",
    )
    parser.add_argument(
        "--archive-dir",
        default=None,
        help="Archive destination, default: BACKUPS_DIR/archive",
    )
    parser.add_argument(
        "--min-size-bytes",
        type=int,
        default=MIN_BACKUP_SIZE_BYTES,
        help="Archive backups smaller than this size, default: 1024",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Move files into the archive directory. Defaults to dry-run.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = archive_tiny_backups(
        backups_dir=args.backups_dir,
        archive_dir=args.archive_dir,
        min_size_bytes=args.min_size_bytes,
        apply=args.apply,
    )
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
