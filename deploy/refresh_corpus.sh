#!/usr/bin/env bash
#
# Deck Doctor — one bounded corpus-refresh cycle, suitable for a daily timer.
#
# Runs the full SP3 pipeline end-to-end on the production VPS:
#   1. SCRAPE  a bounded batch of new decklists (newest-first per source;
#              the EDHREC seeds pass is disabled). Each source is best-effort:
#              a failing source is logged and the cycle continues.
#   2. LOAD    the grown JSONL into decks.sqlite + edhrec.sqlite (idempotent,
#              purely additive — never shrinks the corpus).
#   3. REBUILD the scoring tables: build_relationships then build_cooccurrence.
#   4. PUSH    the SQLite artifacts into the deckdoctor Postgres DB.
#   5. RELOAD  the live backend (POST /admin/reload) so the new tables go live
#              WITHOUT a restart.
#
# Designed for: ExecStart of deckdoctor-refresh.service (oneshot), WorkingDirectory
# /opt/deck-doctor, User simmander. All output goes to stdout/stderr so the systemd
# journal captures it. NOT the Windows-dev tools/refresh_loop.py (which hardcodes
# C:/ combo-catalog paths and only knows archidekt/moxfield).
#
# Environment (with safe defaults):
#   PY            python interpreter            (default /opt/deck-doctor/.venv/bin/python)
#   APP_DIR       working dir                   (default /opt/deck-doctor)
#   API           backend base URL              (default http://localhost:8002)
#   DATABASE_URL  deckdoctor Postgres DSN       (passed through to load_to_postgres;
#                 the systemd unit sets this to the same DSN as deckdoctor-api)
#   RECENT_MAX    new decks per source per pass (default 150)
#   SEED_TOP / SEED_DECKS_PER / SEED_MAX_COMMANDERS  (seeds breadth pass knobs)
#   COMBO_CATALOG / KNOWN_COMBOS  optional combo-catalog JSON paths (used only if
#                 the files exist; the VPS normally has none — that is fine)
#   SKIP_REBUILD  if "1", scrape + load only (cheap dry run; skips rebuild/push/reload)
#   DATA_LOCK     lock shared with deckdoctor-cardupdate and deploy.sh
#                 (default $APP_DIR/data/.pipeline.lock)
#   LOCK_WAIT     seconds to wait for it before failing (default 7200)
#
# Steps 3-5 live in deploy/rebuild_and_reload.sh (shared with tools/card_update).

set -uo pipefail   # NOT -e: a single source/step failure must not abort the cycle.

PY="${PY:-/opt/deck-doctor/.venv/bin/python}"
APP_DIR="${APP_DIR:-/opt/deck-doctor}"
API="${API:-http://localhost:8002}"
RECENT_MAX="${RECENT_MAX:-150}"
SEED_TOP="${SEED_TOP:-100}"
SEED_DECKS_PER="${SEED_DECKS_PER:-15}"
SEED_MAX_COMMANDERS="${SEED_MAX_COMMANDERS:-100}"
COMBO_CATALOG="${COMBO_CATALOG:-}"
KNOWN_COMBOS="${KNOWN_COMBOS:-}"
SKIP_REBUILD="${SKIP_REBUILD:-0}"
DATA_LOCK="${DATA_LOCK:-$APP_DIR/data/.pipeline.lock}"
LOCK_WAIT="${LOCK_WAIT:-7200}"

# Sources walked newest-first. archidekt, moxfield and edhrec (incl. the seeds pass) are
# DISABLED since 2026-11-24: their robots/terms forbid automated access (see
# docs/plans/2026-11-24-edhrec-compliance.md). The four below have UNKNOWN terms; they stay
# until someone fetches and reads them.
RECENT_SOURCES=(tappedout deckstats aetherhub manastack)
# After a site grants written permission (tools/scrape_decklists/permissions.json), add it
# here without editing this file, e.g. EXTRA_RECENT_SOURCES="archidekt". The runner still
# refuses any source whose host has no grant, so a typo here cannot bypass the block.
# shellcheck disable=SC2206
RECENT_SOURCES+=(${EXTRA_RECENT_SOURCES:-})
ENABLE_SEEDS="${ENABLE_SEEDS:-0}"   # 1 = EDHREC seeds pass (needs an edhrec.com grant)

cd "$APP_DIR" || { echo "[refresh] FATAL: cannot cd to $APP_DIR" >&2; exit 1; }

log() { echo "[refresh $(date -u +%H:%M:%S)] $*"; }

# One data job at a time (deckdoctor-cardupdate rewrites cards.json + scores.sqlite).
# Wait for it, then fail loudly rather than silently skipping the cycle.
[ -e "$DATA_LOCK" ] || : > "$DATA_LOCK" || { log "FATAL: cannot create $DATA_LOCK"; exit 1; }
exec 9<"$DATA_LOCK" || { log "FATAL: cannot open $DATA_LOCK"; exit 1; }
if ! flock -w "$LOCK_WAIT" 9; then
  log "FATAL: $DATA_LOCK still held after ${LOCK_WAIT}s (card update or deploy running) — cycle not run"
  exit 1
fi

decks_count() {
  "$PY" - <<'PYEOF' 2>/dev/null || echo "?"
import sqlite3
try:
    print(sqlite3.connect("data/decks.sqlite").execute("SELECT count(*) FROM decks").fetchone()[0])
except Exception:
    print("?")
PYEOF
}

CYCLE_START=$(date +%s)
log "cycle start (recent_max=$RECENT_MAX, seed_top=$SEED_TOP, skip_rebuild=$SKIP_REBUILD)"
BEFORE=$(decks_count)
log "corpus decks BEFORE: $BEFORE"

# ── 1. SCRAPE — newest-first per source (best-effort) ─────────────────────────
for src in "${RECENT_SOURCES[@]}"; do
  log "scrape recent: $src (max $RECENT_MAX)"
  if "$PY" tools/scrape_decklists/runner.py recent \
        --recent-source "$src" --max "$RECENT_MAX" \
        --saturate-pages 5 --batch refresh; then
    log "scrape recent: $src OK"
  else
    log "scrape recent: $src FAILED (continuing)"
  fi
done

# ── 1b. seeds pass: paused (walks EDHREC deckpreview pages; enable only with a grant
#        from EDHREC on file in permissions.json — we contact each site individually).
if [ "$ENABLE_SEEDS" = "1" ]; then
  log "scrape seeds (max $SEED_MAX_COMMANDERS commanders)"
  if "$PY" tools/scrape_decklists/runner.py seeds --top "$SEED_TOP"         --decks-per "$SEED_DECKS_PER" --max-commanders "$SEED_MAX_COMMANDERS" --batch refresh; then
    log "scrape seeds OK"
  else
    log "scrape seeds FAILED or refused (no grant?) (continuing)"
  fi
else
  log "scrape seeds: disabled (set ENABLE_SEEDS=1 once edhrec.com has a grant)"
fi

# ── 2. LOAD — fold JSONL into the SQLite corpus (additive, idempotent) ─────────
log "load_corpus"
if ! "$PY" tools/scrape_decklists/load_corpus.py; then
  log "load_corpus FAILED — aborting cycle (corpus unchanged in PG)"
  exit 1
fi
AFTER=$(decks_count)
log "corpus decks AFTER load: $AFTER (was $BEFORE)"

if [ "$SKIP_REBUILD" = "1" ]; then
  log "SKIP_REBUILD=1 — scrape+load only; skipping rebuild/push/reload"
  log "cycle done in $(( $(date +%s) - CYCLE_START ))s"
  exit 0
fi

# ── 3-5. REBUILD -> PUSH -> RELOAD (deploy/rebuild_and_reload.sh, shared with the
#         card-update pipeline). We hold the data lock, so the script must not retake it.
if ! PY="$PY" APP_DIR="$APP_DIR" API="$API" COMBO_CATALOG="$COMBO_CATALOG" \
     KNOWN_COMBOS="$KNOWN_COMBOS" LOG_TAG=refresh DD_DATA_LOCK_HELD=1 \
     bash "$APP_DIR/deploy/rebuild_and_reload.sh"; then
  exit 1
fi

log "cycle done in $(( $(date +%s) - CYCLE_START ))s  (corpus $BEFORE -> $AFTER decks)"
