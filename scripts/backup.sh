#!/usr/bin/env bash
# NFR-08 daily backup (runbook §4). Runs INSIDE the postgres container via
# ofelia (ofelia.ini job "backup"; scripts/ and the backups volume are mounted
# there — docker-compose.yml). pg_dump -Fc -> $BACKUP_DIR/tokenops_%F.dump,
# rotate $ROTATE_DAYS, reports/ snapshotted in the same job, optional rclone
# offsite when $RCLONE_REMOTE is set. Uploads are deliberately NOT backed up:
# they purge after 7 days (FR-21) and restoring them would break the FR-23
# promise. Restore drill: runbook §4.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
REPORTS_DIR="${REPORTS_DIR:-/reports}"
ROTATE_DAYS="${ROTATE_DAYS:-14}"
PGUSER="${POSTGRES_USER:-tokenops_cost_auditor}"
PGDATABASE="${POSTGRES_DB:-tokenops_cost_auditor}"
STAMP="$(date -u +%F)"
DUMP="$BACKUP_DIR/tokenops_${STAMP}.dump"

mkdir -p "$BACKUP_DIR"

# write-then-rename so the digest freshness check never counts a partial dump
pg_dump -Fc -U "$PGUSER" "$PGDATABASE" -f "${DUMP}.part"
mv "${DUMP}.part" "$DUMP"

# rotation (dumps and report snapshots)
find "$BACKUP_DIR" -maxdepth 1 -name 'tokenops_*.dump' -mtime "+${ROTATE_DAYS}" -delete
find "$BACKUP_DIR" -maxdepth 1 -name 'reports_*.tar.gz' -mtime "+${ROTATE_DAYS}" -delete

# reports/ same-job snapshot (runbook §4); rsync when present, tar fallback
# (the postgres image ships neither rsync nor gzip-less tar issues — tar is in coreutils)
if [ -d "$REPORTS_DIR" ]; then
    if command -v rsync >/dev/null 2>&1; then
        rsync -a --delete "$REPORTS_DIR"/ "$BACKUP_DIR/reports/"
    else
        tar -czf "$BACKUP_DIR/reports_${STAMP}.tar.gz" -C "$REPORTS_DIR" .
    fi
fi

# offsite copy (B2/R2 free tier), env-gated; absence is not an error —
# the digest surfaces backup age, runbook §8 covers offsite setup at deploy
if [ -n "${RCLONE_REMOTE:-}" ] && command -v rclone >/dev/null 2>&1; then
    rclone copy "$BACKUP_DIR" "$RCLONE_REMOTE" --include "tokenops_${STAMP}.dump"
fi

echo "backup: OK ${DUMP} ($(du -h "$DUMP" | cut -f1))"
