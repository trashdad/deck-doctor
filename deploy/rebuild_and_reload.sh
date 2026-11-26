#!/usr/bin/env bash
#
# Deck Doctor — rebuild the deck-driven scoring tables, push every SQLite artifact into
# Postgres, and hot-reload the API. Steps 3-5 of the nightly refresh, shared by:
#   * deploy/refresh_corpus.sh          (deckdoctor-refresh, after scrape + load_corpus)
#   * tools/card_update (rebuild stage) (deckdoctor-cardupdate, after promoting new card data)
#
#   3. REBUILD build_relationships then build_cooccurrence on data/scores.sqlite
#   4. PUSH    tools/load_to_postgres.py (all data/*.sqlite -> the deckdoctor DB)
#   5. RELOAD  POST $API/admin/reload (new tables + card files go live without a restart)
#
# Data jobs share one lock ($DATA_LOCK). Callers that already hold it export
# DD_DATA_LOCK_HELD=1; run by hand, this script takes the lock itself.
#
# Environment (same names and defaults as refresh_corpus.sh):
#   PY APP_DIR API DATABASE_URL COMBO_CATALOG KNOWN_COMBOS
#   LOG_TAG        log prefix (default "rebuild"; refresh_corpus.sh passes "refresh")
#   DATA_LOCK      shared lock file (default $APP_DIR/data/.pipeline.lock)
#   LOCK_WAIT      seconds to wait for the lock when taking it here (default 3600)

set -uo pipefail

PY="${PY:-/opt/deck-doctor/.venv/bin/python}"
APP_DIR="${APP_DIR:-/opt/deck-doctor}"
API="${API:-http://localhost:8002}"
COMBO_CATALOG="${COMBO_CATALOG:-}"
KNOWN_COMBOS="${KNOWN_COMBOS:-}"
LOG_TAG="${LOG_TAG:-rebuild}"
DATA_LOCK="${DATA_LOCK:-$APP_DIR/data/.pipeline.lock}"
LOCK_WAIT="${LOCK_WAIT:-3600}"

cd "$APP_DIR" || { echo "[$LOG_TAG] FATAL: cannot cd to $APP_DIR" >&2; exit 1; }

log() { echo "[$LOG_TAG $(date -u +%H:%M:%S)] $*"; }

if [ "${DD_DATA_LOCK_HELD:-0}" != "1" ]; then
  [ -e "$DATA_LOCK" ] || : > "$DATA_LOCK" || { log "FATAL: cannot create $DATA_LOCK"; exit 1; }
  exec 9<"$DATA_LOCK" || { log "FATAL: cannot open $DATA_LOCK"; exit 1; }
  if ! flock -w "$LOCK_WAIT" 9; then
    log "FATAL: $DATA_LOCK still held after ${LOCK_WAIT}s (refresh, card update or deploy running)"
    exit 1
  fi
fi

# ── 3. REBUILD — scoring tables (relationships then co-occurrence) ─────────────
REL_ARGS=(scoring/build_relationships.py --db data/scores.sqlite)
for cat in "$COMBO_CATALOG" "$KNOWN_COMBOS"; do
  [ -z "$cat" ] && continue
  if [ -f "$cat" ]; then REL_ARGS+=(--catalog "$cat")
  else log "WARNING: combo catalog $cat is configured but missing -> fewer asserted combos"; fi
done
log "build_relationships: ${REL_ARGS[*]}"
if ! "$PY" "${REL_ARGS[@]}"; then
  log "build_relationships FAILED — aborting before push (live tables untouched)"
  exit 1
fi

log "build_cooccurrence (min-support 20)"
if ! "$PY" scoring/build_cooccurrence.py --scores data/scores.sqlite \
      --decks data/decks.sqlite --edhrec data/edhrec.sqlite --min-support 20; then
  log "build_cooccurrence FAILED — aborting before push (live tables untouched)"
  exit 1
fi

# ── 4. PUSH — mirror SQLite artifacts into the deckdoctor Postgres DB ──────────
log "load_to_postgres"
if ! "$PY" tools/load_to_postgres.py; then
  log "load_to_postgres FAILED — live backend still serving the previous tables"
  exit 1
fi

# ── 5. RELOAD — swap in the new tables without a restart ───────────────────────
log "reload backend ($API/admin/reload)"
RELOAD_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/admin/reload" --max-time 120 || echo "000")
if [ "$RELOAD_CODE" = "200" ]; then
  log "reload OK (HTTP 200)"
else
  log "reload returned HTTP $RELOAD_CODE — backend may need a manual reload"
  exit 1
fi
