#!/usr/bin/env bash
# One-time DEEP crawl to front-load the corpus toward ~50k decks.
#
# Scrape + load ONLY — no score rebuild and no Postgres push. The nightly
# deckdoctor-refresh job (or a manual trigger) does the heavy rebuild → push →
# reload once, after this has bulked up the corpus. Keeping the two separate is
# what makes a big crawl cheap: we pay the O(corpus^2) rebuild a single time.
#
# COMPLIANCE (2026-11-24): EDHREC, Archidekt and Moxfield are NOT scraped any more.
# EDHREC's robots.txt disallows /deckpreview/ and its Terms of Use forbid automated
# queries and downloading; Archidekt's Terms ban automated queries; no Moxfield
# terms permitting this were found. The old EDHREC "seeds" step and the Archidekt
# walk were removed from this script, and runner.py now refuses those hosts.
# See docs/plans/2026-11-24-edhrec-compliance.md.
#
# The remaining sources (TappedOut, Deckstats) have NOT had their terms checked
# (UNKNOWN). Do not run this script until someone has read and recorded them.
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
#    archidekt removed 2026-11-24 (compliance; see header).
for src in tappedout deckstats; do
  log "recent: $src (max 2000)"
  "$PY" tools/scrape_decklists/runner.py recent \
      --recent-source "$src" --max 2000 --saturate-pages 12 --batch frontload \
    || log "recent $src failed (continuing)"
done

# 2. (removed 2026-11-24) The EDHREC commander-breadth "seeds" pass is disabled for
#    compliance (docs/plans/2026-11-24-edhrec-compliance.md). Do not re-add it
#    without written permission from EDHREC.

# 3. Fold everything into the corpus DBs (idempotent). No rebuild/push here.
log "load_corpus"
"$PY" tools/scrape_decklists/load_corpus.py || log "load_corpus FAILED"

log "DONE — corpus(sqlite) after: $(sqlite_decks)  (run the nightly refresh, or trigger deckdoctor-refresh.service, to rebuild+push+reload)"
