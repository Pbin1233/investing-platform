#!/bin/sh
set -eu

BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
DATE="$(date +%Y-%m-%d_%H-%M-%S)"
FILE="$BACKUP_DIR/investing_$DATE.sql.gz"

POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-investing}"
POSTGRES_USER="${POSTGRES_USER:-investing}"

if [ -z "${POSTGRES_PASSWORD:-}" ]; then
  echo "POSTGRES_PASSWORD is not set."
  exit 1
fi

mkdir -p "$BACKUP_DIR"

PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
  -h "$POSTGRES_HOST" \
  -p "$POSTGRES_PORT" \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  | gzip > "$FILE"

if [ ! -s "$FILE" ]; then
  echo "Backup failed or empty file created."
  rm -f "$FILE"
  exit 1
fi

echo "Backup created: $FILE"
