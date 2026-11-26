#!/usr/bin/env bash
# Deck Doctor — nightly database backup (ExecStart of deckdoctor-backup.service).
#
#   1. tower (on-site NAS):  tools/backup_db.py — pg_dump -Fc, scp to
#      $BACKUP_DEST, keep the newest 14. Runs as $APP_USER, whose SSH key tower trusts.
#   2. off-site (restic):  for each env file in $RESTIC_ENV (space-separated; since
#      2026-11-24 chimera + jupiter, append-only rest-servers that replaced callisto,
#      see simmander-hub infra/rest-server): pg_dump (as postgres, peer auth, no DB
#      password) piped straight into `restic backup --stdin-from-command`. restic
#      aborts the snapshot if pg_dump fails, so a truncated dump can never be saved
#      as a good one. Uncompressed (-Z0) so restic can dedup it.
#
# The destinations are independent: any can fail without skipping the others;
# the unit fails (exit 1) if any did. Runs as root: step 2 reads the root-only
# restic env files (RESTIC_REPOSITORY + RESTIC_PASSWORD_FILE, and for a
# rest-server RESTIC_REST_USERNAME / RESTIC_REST_PASSWORD).
#
# Retention: tower is pruned by backup_db.py (--keep). The off-site repos are
# append-only; each server prunes its own repos (restic-maintenance).

set -uo pipefail

APP_DIR="${APP_DIR:-/opt/deck-doctor}"
APP_USER="${APP_USER:-simmander}"
DB_NAME="${DB_NAME:-deckdoctor}"
KEEP="${KEEP:-14}"
RESTIC_ENV="${RESTIC_ENV:-/etc/deck-doctor/restic.env}"
RESTIC="${RESTIC:-/usr/local/bin/restic}"
RESTIC_HOST="${RESTIC_HOST:-simtrack}"

log() { echo "[backup $(date -u +%H:%M:%S)] $*"; }
rc=0

# Never dump while a data job (card update / refresh / deploy) is rewriting the tables:
# load_to_postgres commits per store, so a concurrent dump could mix old and new stores.
# Wait for the shared lock (bounded), then fail loudly rather than skip the backup.
DATA_LOCK="${DATA_LOCK:-$APP_DIR/data/.pipeline.lock}"
LOCK_WAIT="${LOCK_WAIT:-900}"   # deckdoctor-backup.service has TimeoutStartSec=1800
[[ -e "$DATA_LOCK" ]] || runuser -u "$APP_USER" -- touch "$DATA_LOCK" || { log "FATAL: cannot create $DATA_LOCK"; exit 1; }
exec 9<"$DATA_LOCK" || { log "FATAL: cannot open $DATA_LOCK"; exit 1; }
if ! flock -w "$LOCK_WAIT" 9; then
    log "FAILED: $DATA_LOCK still held after ${LOCK_WAIT}s (card update / refresh / deploy) — no backup taken"
    exit 1
fi

# ── 1. tower ───────────────────────────────────────────────────────────────────
log "tower: tools/backup_db.py --keep $KEEP"
if runuser -u "$APP_USER" -- "$APP_DIR/.venv/bin/python" "$APP_DIR/tools/backup_db.py" --keep "$KEEP"; then
    log "tower: OK"
else
    log "tower: FAILED"; rc=1
fi

# ── 2. off-site (restic, one repo per env file) ────────────────────────────────
for env_file in $RESTIC_ENV; do
    site=$(basename "$env_file" .env)
    if [[ ! -r "$env_file" ]]; then
        log "$site: FAILED — $env_file missing/unreadable"; rc=1; continue
    fi
    (
        set -a; . "$env_file"; set +a
        # systemd gives root no $HOME; without a cache restic re-downloads the index every run.
        export RESTIC_CACHE_DIR="${RESTIC_CACHE_DIR:-/var/cache/deck-doctor/restic-$site}"
        if ! "$RESTIC" cat config >/dev/null 2>&1; then
            log "$site: repository not initialised — restic init"
            "$RESTIC" init >/dev/null || { log "$site: restic init FAILED"; exit 1; }
        fi
        log "$site: pg_dump $DB_NAME | restic backup"
        if "$RESTIC" backup --no-scan --stdin-from-command --stdin-filename "$DB_NAME.dump" \
                --tag pg --tag nightly --host "$RESTIC_HOST" -- \
                runuser -u postgres -- pg_dump -Fc -Z0 --no-owner --no-acl "$DB_NAME"; then
            log "$site: OK — $("$RESTIC" snapshots --latest 1 --host "$RESTIC_HOST" --compact 2>/dev/null | sed -n '3p')"
        else
            log "$site: FAILED"; exit 1
        fi
    ) || rc=1
done

exit $rc
