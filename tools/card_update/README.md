# card_update — automated card-data pipeline

New MTG sets flow into Deck Doctor with no human step. Every run either promotes a
verified new card layer, finds nothing to do, or **fails closed** (live data untouched,
or automatically rolled back) and **fails loud** (exit ≠ 0 → systemd `OnFailure` alert).

```bash
cd /opt/deck-doctor
PYTHONPATH=tools .venv/bin/python -m card_update run            # what the timer runs
PYTHONPATH=tools .venv/bin/python -m card_update check          # anything new upstream?
PYTHONPATH=tools .venv/bin/python -m card_update status         # exit 1 if stale / unresolved
PYTHONPATH=tools .venv/bin/python -m card_update recover [--files-only]   # finish/undo an interrupted change
PYTHONPATH=tools .venv/bin/python -m card_update rollback [--to RELEASE_ID] [--no-rebuild]
PYTHONPATH=tools .venv/bin/python -m card_update gc             # retention
PYTHONPATH=tools .venv/bin/python -m card_update init [--mtgish-sha SHA] [--baseline-from-store|--scoring-code-current]
```

`run` flags: `--dry-run` (describe each stage; no network, files or lock), `--no-promote`
(build + verify, keep the candidate), `--only a,b`, `--skip a,b`, `--resume RUN_ID`
(continue a failed run in its own dir; finished stages are skipped), `--from-stage S`
(with `--resume`), `--force` (continue although nothing changed), `--waive GATE` (manual
runs: log that gate's violations as WAIVED). `--config PATH` works on every command.

**Exit codes:** 0 success *or* nothing-to-do (the last log line says which: `RESULT: PROMOTED`,
`RESULT: nothing to do`, `RESULT: success (no promotion)`), 1 stage failure / gate violation /
rolled back, 2 config or usage error, 3 lock timeout.

## Stages (`stages/`, one job each, in this order)

| # | stage | does | writes |
|---|---|---|---|
| 1 | check | Scryfall bulk `updated_at` + MTGish commit (HEAD or pinned) vs state; nothing-to-do if both unchanged | — |
| 2 | fetch | default-cards `.jsonl.gz` (size = bulk metadata, sha256 recorded), `mtgish.lines.<sha>.json`, MTGish `LICENSE` (must still say MIT) | run dir |
| 3 | prep | stream JSONL → JSON array (prep_cards' own filter), `scoring/prep_cards.py --keep-ids-from <live>`; nothing-to-do if identical to live and MTGish unchanged | run dir |
| 4 | enrich | land prices/produced_mana via Scryfall `/cards/collection` (enrich_lands logic, 75/batch, ≥0.15 s apart); fails on > `max_error_batches` failed batches | run dir |
| 5 | build | `build_store` → `build_semantics` → `build_fingerprints` into a candidate `scores.sqlite` | run dir |
| 6 | verify | all gates (`gates.py`); any violation stops the run | — |
| 7 | approve | optional manual gate (off by default) | — |
| 8 | promote | refuse if live ≠ recorded release; snapshot live as a backup release; open the durable transaction; fsync + `os.replace` candidates over the live files | live + releases |
| 9 | rebuild | `deploy/rebuild_and_reload.sh` (relationships, co-occurrence, Postgres, `/admin/reload`) | Postgres |
| 10 | health | rebuilt tables `card_relationships`/`engines`/`card_cooccurrence` non-empty and not shrunk > `max_shrink_ratio`; `/health` `status ok`, `scores_loaded`, `cards` == candidate, `engines` > 0, no collapsed `engines`/`edhrec_commanders`/`spellbook_combos` vs before | — |
| 11 | cleanup | retention of releases, run dirs, logs (**non-fatal**: a failure is a warning) | — |

**Transactions.** Every live change (promote, rollback) is recorded in `state.json`
(`transaction`: kind, `restore_to`, `needs_rebuild`, phase) *before* the first live file
changes, and cleared only when the change is consistent end to end: after rebuild + health,
or immediately when Postgres was never touched. Any fatal failure while the run's
transaction is open reverts it (restore `restore_to`, plus rebuild + health once Postgres
was touched) and exits 1; the log says "live data unchanged" only when no live file
changed. An interrupted change (crash, kill, power loss, `rollback --no-rebuild`) is
resolved by whoever comes next: the API's `ExecStartPre` (`recover --files-only`: files
only, skipped while a job holds the lock), `card_update recover`, or the next run (which
then exits 1 so it is noticed). Child processes run in their own process group and are
killed as a group on timeout/SIGTERM before any revert starts; a second SIGTERM is ignored
so the revert can finish (`TimeoutStopSec` bounds it). `run.deadline_hours` caps the run.

## Gates (verify)

cards.json parses; required fields (`id name oracle_id type_line color_identity cmc`);
no duplicate ids/oracle_ids; count within `[min_count_ratio, max_count_ratio]` of live and ≥
`min_cards`; every surviving oracle_id keeps its card id (user decks store ids); sentinel
cards present; tagged-card share drops ≤ `max_tag_share_drop_pp`; ≤ `max_lost_all_tags_ratio`
of previously tagged cards lose all tags; ≤ `max_new_unmapped_operators` MTGish operators
that are unmapped now but were not in the live release's recorded set (first run records the
set; `max_unmapped_operators` is an absolute ceiling); IER identical for cards whose data did
not change (≤ `max_ier_changed_unchanged`) — enforced only while the scoring-code
fingerprint (`fingerprint.py`: build_store.py + simmander_scoring/*) recorded with the live
release equals the current code's, otherwise logged as a WARNING and re-baselined on
promote; candidate `integrity_check` ok, required tables non-empty, store card ids ==
cards.json ids, every card has an IER; land_meta covers ≥ `min_land_meta_coverage` of lands.
Each gate logs its numbers; a successful promotion logs the new-content summary (new
cards, new set codes, removed, renamed).

## Files

```
/opt/deck-doctor/card-data/          (untracked; deploy.sh never touches it)
  current/cards.json, land_meta.json, PROVENANCE.json   <- SIMMANDER_CARDS / SIMMANDER_LAND_META
  releases/<release-id>/             backup snapshots (cards, land_meta, scores, release.json)
  runs/<run-id>/                     downloads, candidates, manifest.json (per-stage record)
  logs/<run-id>.log                  per-run log (also in journalctl -u deckdoctor-cardupdate)
  state.json                         live release, upstream versions, failure counter, open transaction,
                                     scoring fingerprint, unmapped-operator baseline sha
  unmapped/<sha256>.json             recorded unmapped-operator sets (baseline for "new operators")
  approvals/<run-id>.approved        only when the approval gate is on
/opt/deck-doctor/data/scores.sqlite  live store (load_to_postgres reads it there)
/opt/deck-doctor/data/.pipeline.lock shared with refresh_corpus.sh and deploy.sh
```

`PROVENANCE.json` and every `release.json` record sources, commit, sha256s and the MTGish
MIT licence text.

## Config

JSON (`card_update.example.json` lists every key with its default) plus env overrides
`CARD_UPDATE__<SECTION>__<KEY>=<json>` (e.g. `CARD_UPDATE__APPROVE__ENABLED=true`). Unknown
keys and out-of-range values are rejected (exit 2). Production needs no file. Sections:
`paths` (null = derived from `app_dir`; live paths follow `SIMMANDER_CARDS` /
`SIMMANDER_LAND_META`), `upstream` (URLs, generic User-Agent, `mtgish_pin_sha`), `http`
(timeouts, bounded retries/backoff, ≥ 0.1 s per host), `lock.wait_minutes`, `fetch` (size
bounds, free disk), `prep`, `enrich`, `build`, `gates`, `approve`, `rebuild`, `health`,
`retention` (`keep_releases` 3, `keep_runs` 5, `keep_log_days` 30), `status.stale_after_days`,
`stages.order` / `stages.allow_partial_promote`, `run.deadline_hours`. Downloads only go to
`https` hosts in `http.allowed_hosts` (redirects included); JSON bodies are capped
(`http.max_json_bytes`); the bulk file is streamed as JSON lines with caps on decompressed
bytes and lines. Child output is logged with `password=`/`user:pass@` redacted.

## Plugging stages in and out

`stages.order` lists the stages to run. `enrich`, `approve` and `cleanup` may be removed
(without `enrich`, the live land_meta is kept). `check fetch prep build verify promote` are
mandatory, and so are `rebuild` + `health` unless `stages.allow_partial_promote` is true
(rehearsals only: such runs end `partial`, upstream stamps are not advanced). Built-ins keep
their order; `approve.enabled` requires `approve` in the order. A custom stage is a
`card_update.stages.base.Stage` subclass with a `name`, `describe(ctx)` and `run(ctx) ->
StageResult`, listed as `"package.module:ClassName"` (importable via `PYTHONPATH`). Read
inputs from `ctx.artifacts` / `ctx.config`, write only inside `ctx.workdir`, raise
`StageError` with an actionable message, cap child timeouts with `ctx.child_timeout(s)`.
A fatal failure after promote reverts the release automatically; set `fatal = False` for
housekeeping that must never undo a release.

## Scoring-code changes and the first production run

`init` records no scoring fingerprint by default, so the first run enforces the IER gate
against the live store. If the live store was built by older scoring code (or you do not
know), seed with `init --baseline-from-store`: the first run then reports IER drift as a
warning and promotes, recording the real fingerprint. `init --scoring-code-current` asserts
the store was built by this checkout's code. After a deploy that changes
`scoring/build_store.py` or `scoring/simmander_scoring/`, the next run warns instead of
blocking and re-baselines.

## Manual approval

Off by default. Enable with `"approve": {"enabled": true}` (or
`CARD_UPDATE__APPROVE__ENABLED=true` in the unit). A run then stops (exit 1, alert) after
verify; review `runs/<run-id>/manifest.json` and the log, then
`touch card-data/approvals/<run-id>.approved` and `run --resume <run-id>`.
`approve.wait_minutes` > 0 makes the stage poll for the file instead of failing at once.

## Rolling back

`rollback` restores the newest backup release (or `--to RELEASE_ID`; list them with
`ls card-data/releases`) as a transaction, re-runs rebuild_and_reload and checks health.
The release being replaced is snapshotted first (only if live matches the recorded release),
so a roll-forward is `rollback --to <that id>`. With `--no-rebuild` the change stays open
until `recover` or the next run rebuilds Postgres. Scryfall
changes daily, so the next timer run will promote fresh data again: to hold an old release,
`systemctl disable --now deckdoctor-cardupdate.timer` until the cause is fixed.

## Tests

`PYTHONPATH=tools python -m pytest tools/card_update/tests -q` — network blocked by an
autouse fixture; the end-to-end tests run the real scoring scripts on a tiny fixture
(`tests/fixtures/`, 14 Scryfall prints + their MTGish lines) with faked network, rebuild
script and API.
