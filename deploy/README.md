# Deploy (SP11) — SCAFFOLD

Implement per `docs/superpowers/plans/2026-06-10-sp6-sp11-roadmap.md` §SP11.

```bash
docker compose -f deploy/compose.yaml up --build   # app on :3000
```

## Data-volume contract

The backend container mounts the repo `data/` directory **read-only** at `/app/data`.
These files must exist on the host before first run (none are baked into images):

| File | Produced by |
|---|---|
| `data/cards.json` | committed (21 MB) |
| `data/scores.sqlite` | `scoring/build_store.py` + `build_relationships.py` + `build_cooccurrence.py` |
| `data/decks.sqlite` | `tools/scrape_decklists/load_corpus.py` |
| `data/edhrec.sqlite` | **No longer produced** (EDHREC scraping disabled 2026-11-24; see `docs/plans/2026-11-24-edhrec-compliance.md`). Existing local copies are historical. Run the backend with `DECKDOCTOR_EDHREC_SIGNAL=off` to ignore `edhrec_metrics`. |
| `data/spellbook.sqlite` | `tools/import_spellbook/runner.py` + `load_spellbook.py` |
| `data/userdecks.sqlite` | created on demand by the backend — mount `data/` **read-write** for just this file, or point `SIMMANDER_USERDECKS` at a separate writable volume (preferred: a named volume mounted at `/app/userdata`) |

## Rebuild pipeline order (when refreshing the corpus)

> Do **not** scrape EDHREC, Archidekt or Moxfield to refresh the corpus: their robots.txt /
> Terms forbid it and `tools/scrape_decklists/runner.py` refuses those hosts. Other deck
> sites' terms are UNKNOWN. See `docs/plans/2026-11-24-edhrec-compliance.md`. The
> `--edhrec` input below folds EDHREC numbers into `synergy_ab/ba`; to rebuild without
> EDHREC, point it at a SQLite file whose `edhrec_metrics` table is empty (a missing file
> errors — `edhrec_from_db` opens it read-only).

```
tools/scrape_decklists/load_corpus.py
scoring/build_relationships.py --db data/scores.sqlite --catalog ... (see NEXT_SESSION.md)
scoring/build_cooccurrence.py  --scores data/scores.sqlite --decks data/decks.sqlite --edhrec data/edhrec.sqlite --min-support 20
tools/import_spellbook/runner.py && tools/import_spellbook/load_spellbook.py
```
