#!/usr/bin/env bash
#
# Deck Doctor — one bounded corpus-refresh cycle, suitable for a daily timer.
#
# Runs the full SP3 pipeline end-to-end on the production VPS:
#   1. SCRAPE  a bounded batch of new decklists (newest-first per source +
#              one commander-breadth seeds pass). Each source is best-effort:
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

# Working sources to walk newest-first. Moxfield is intentionally absent (it is
# collected indirectly via EDHREC deckpreview in the seeds pass).
RECENT_SOURCES=(archidekt tappedout deckstats aetherhub manastack)

cd "$APP_DIR" || { echo "[refresh] FATAL: cannot cd to $APP_DIR" >&2; exit 1; }

log() { echo "[refresh $(date -u +%H:%M:%S)] $*"; }

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

# ── 1b. SCRAPE — one commander-breadth seeds pass (best-effort) ────────────────
log "scrape seeds: top $SEED_TOP, decks-per $SEED_DECKS_PER, max-commanders $SEED_MAX_COMMANDERS"
if "$PY" tools/scrape_decklists/runner.py seeds \
      --top "$SEED_TOP" --decks-per "$SEED_DECKS_PER" \
      --max-commanders "$SEED_MAX_COMMANDERS" --batch refresh; then
  log "scrape seeds OK"
else
  log "scrape seeds FAILED (continuing)"
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

# ── 3. REBUILD — scoring tables (relationships then co-occurrence) ─────────────
REL_ARGS=(scoring/build_relationships.py --db data/scores.sqlite)
[ -n "$COMBO_CATALOG" ] && [ -f "$COMBO_CATALOG" ] && REL_ARGS+=(--catalog "$COMBO_CATALOG")
[ -n "$KNOWN_COMBOS" ]  && [ -f "$KNOWN_COMBOS" ]  && REL_ARGS+=(--catalog "$KNOWN_COMBOS")
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

log "cycle done in $(( $(date +%s) - CYCLE_START ))s  (corpus $BEFORE -> $AFTER decks)"
