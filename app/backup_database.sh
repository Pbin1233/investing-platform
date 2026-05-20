#!/bin/sh

BACKUP_DIR="/data/backups"
DATE="$(date +%Y-%m-%d_%H-%M-%S)"
FILE="$BACKUP_DIR/investing_$DATE.sql.gz"

mkdir -p "$BACKUP_DIR"

PGPASSWORD="change_this_password" pg_dump \
  -h postgres \
  -U investing \
  -d investing \
  | gzip > "$FILE"

if [ ! -s "$FILE" ]; then
  echo "Backup failed or empty file created."
  rm -f "$FILE"
  exit 1
fi

echo "Backup created: $FILE"
