#!/usr/bin/env bash
# Daily PostgreSQL backup using docker exec.
#
# Setup (run once on the server):
#   chmod +x /opt/message_scheduler/deploy/backup.sh
#   (crontab -l 2>/dev/null; echo "0 3 * * * /opt/message_scheduler/deploy/backup.sh >> /var/log/pgbackup.log 2>&1") | crontab -
#
# Manual restore:
#   zcat /opt/backups/postgres/<file>.sql.gz | docker exec -i global_db psql -U msched message_scheduler

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/opt/backups/postgres}"
KEEP_DAYS="${KEEP_DAYS:-7}"
CONTAINER="${CONTAINER:-global_db}"
DB_USER="${POSTGRES_USER:-msched}"
DB_NAME="${POSTGRES_DB:-message_scheduler}"

mkdir -p "$BACKUP_DIR"
FILE="$BACKUP_DIR/backup_$(date +%Y%m%d_%H%M%S).sql.gz"

docker exec "$CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$FILE"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)  backup written: $FILE"

find "$BACKUP_DIR" -name '*.sql.gz' -mtime +"$KEEP_DAYS" -delete
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)  pruned: kept last ${KEEP_DAYS} days"
