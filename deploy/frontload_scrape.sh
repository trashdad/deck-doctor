#!/usr/bin/env bash
# One-time DEEP crawl to front-load the corpus toward ~50k decks.
#
# Scrape + load ONLY — no score rebuild and no Postgres push. The nightly
# deckdoctor-refresh job (or a manual trigger) does the heavy rebuild → push →
# reload once, after this has bulked up the corpus. Keeping the two separate is
# what makes a big crawl cheap: we pay the O(corpus^2) rebuild a single time.
#
# Sources: the high-yield, lower-risk ones. The real volume comes from EDHREC
# commander-breadth seeds (thousands of commanders, each linking real decklists);
# the date-ordered "recent" walks saturate quickly and just top off the live meta.
# AetherHub/ManaStack are skipped here (low yield + Cloudflare) — the nightly job
# still covers them for freshness.
#
# Detached run (survives SSH/logout, journaled):
#   systemd-run --unit=ddr-frontload --uid=simmander -p WorkingDirectory=/opt/deck-doctor \
#     /opt/deck-doctor/deploy/frontload_scrape.sh
#   journalctl -u ddr-frontload -f
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
PY=.venv/bin/python
log() { echo "[frontload $(date -u +%H:%M:%S)] $*"; }
sqlite_decks() { "$PY" - <<'PY' 2>/dev/null || echo "?"
import sqlite3
try:
    print(sqlite3.connect("data/decks.sqlite").execute("SELECT count(*) FROM decks").fetchone()[0])
except Exception:
    print("?")
PY
}

log "START — corpus(sqlite) before: $(sqlite_decks)"

# 1. Deep recent walks (date-ordered; finite — they saturate and stop).
for src in archidekt tappedout deckstats; do
  log "recent: $src (max 2000)"
  "$PY" tools/scrape_decklists/runner.py recent \
      --recent-source "$src" --max 2000 --saturate-pages 12 --batch frontload \
    || log "recent $src failed (continuing)"
done

# 2. The big lever — EDHREC commander-breadth seeds. json.edhrec.com is CDN-backed
#    and tolerant; the runner throttles per-host. This is where the volume is.
log "seeds: EDHREC breadth (top 1500 commanders, 60 decks each)"
"$PY" tools/scrape_decklists/runner.py seeds \
    --top 1500 --decks-per 60 --max-commanders 1500 --batch frontload \
  || log "seeds failed"

# 3. Fold everything into the corpus DBs (idempotent). No rebuild/push here.
log "load_corpus"
"$PY" tools/scrape_decklists/load_corpus.py || log "load_corpus FAILED"

log "DONE — corpus(sqlite) after: $(sqlite_decks)  (run the nightly refresh, or trigger deckdoctor-refresh.service, to rebuild+push+reload)"
