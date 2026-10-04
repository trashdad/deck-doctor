#!/usr/bin/env bash
# Deck Doctor — nightly database backup (ExecStart of deckdoctor-backup.service).
#
#   1. tower (on-site NAS):  tools/backup_db.py — pg_dump -Fc, scp to
#      $BACKUP_DEST, keep the newest 14. Runs as $APP_USER, whose SSH key tower trusts.
#   2. callisto (off-site):  pg_dump (as postgres, peer auth — no DB password) piped
#      straight into `restic backup --stdin-from-command` on callisto's append-only
#      rest-server. restic aborts the snapshot if pg_dump fails, so a truncated dump
#      can never be saved as a good one. Uncompressed (-Z0) so restic can dedup it.
#
# The two destinations are independent: either can fail without skipping the other;
# the unit fails (exit 1) if either did. Runs as root: step 2 reads the root-only
# restic env ($RESTIC_ENV: RESTIC_REPOSITORY + RESTIC_PASSWORD_FILE).
#
# Retention: tower is pruned by backup_db.py (--keep). The callisto repo is
# append-only, so `restic forget/prune` must be run from a host with delete rights.

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

# ── 1. tower ───────────────────────────────────────────────────────────────────
log "tower: tools/backup_db.py --keep $KEEP"
if runuser -u "$APP_USER" -- "$APP_DIR/.venv/bin/python" "$APP_DIR/tools/backup_db.py" --keep "$KEEP"; then
    log "tower: OK"
else
    log "tower: FAILED"; rc=1
fi

# ── 2. callisto (restic) ───────────────────────────────────────────────────────
if [[ ! -r "$RESTIC_ENV" ]]; then
    log "callisto: FAILED — $RESTIC_ENV missing/unreadable"; exit 1
fi
set -a; . "$RESTIC_ENV"; set +a
if ! "$RESTIC" cat config >/dev/null 2>&1; then
    log "callisto: repository not initialised — restic init"
    "$RESTIC" init >/dev/null || { log "callisto: restic init FAILED"; exit 1; }
fi
log "callisto: pg_dump $DB_NAME | restic backup"
if "$RESTIC" backup --no-scan --stdin-from-command --stdin-filename "$DB_NAME.dump" \
        --tag pg --tag nightly --host "$RESTIC_HOST" -- \
        runuser -u postgres -- pg_dump -Fc -Z0 --no-owner --no-acl "$DB_NAME"; then
    log "callisto: OK — $("$RESTIC" snapshots --latest 1 --host "$RESTIC_HOST" --compact 2>/dev/null | sed -n '3p')"
else
    log "callisto: FAILED"; rc=1
fi

exit $rc
