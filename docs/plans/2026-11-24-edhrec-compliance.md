# EDHREC / Archidekt / Moxfield compliance — 2026-11-24

> **2026-11-25 POLICY CHANGE (supersedes the robots.txt reasoning below, keeps the
> per-site permission machinery).** We no longer rely on robots.txt as a decision input:
> **for testing and development only, robots.txt is ignored and will be respected in the
> future.** Instead we contact each website individually and work with them directly —
> permissions are recorded in `tools/scrape_decklists/permissions.json` and
> `docs/permissions/`, and `runner.py` refuses any host with no grant on file. See
> `docs/robots-policy-2026-11-25.md`. The research findings and switch details below are
> kept as the historical record of what was decided on 2026-11-24.

Status: code changes made in the working tree, **not committed, not deployed**. Production
behaviour is unchanged until the owner deploys **and** sets `DECKDOCTOR_EDHREC_SIGNAL=off`.
This is an engineering note, not legal advice.

## Why

From the sourced research note of 2026-11-24 (fetched pages, quoted there):

- `https://edhrec.com/robots.txt` has `Disallow: /deckpreview/`. The scraper called
  `edhrec.com/api/deckpreview/<hash>`.
- EDHREC Terms of Use (effective 2024-08-06, Space Cow Media) grant a licence "solely for your
  own personal, noncommercial use" and forbid, among others, using "software or automated agents
  or scripts … to generate automated searches, requests, or queries to the Site" and copying or
  downloading any part of the Site.
- No fetched EDHREC page offers a public API, a bulk export or a permission form. The only
  contact path is `contact@edhrec.com` (or the contact form).
- Archidekt's written Terms ban automated queries; no Moxfield terms permitting this use were
  retrieved (the FAQ fetch returned a loading shell).

Things that stay **UNKNOWN** (do not fill them in from memory): `json.edhrec.com/robots.txt`;
whether `json.edhrec.com` is "the Site" under the Terms; whether Deck Doctor counts as
"commercial" under those Terms; the Moxfield Terms/FAQ text; TappedOut, Deckstats, AetherHub and
ManaStack terms; whether `data/edhrec.sqlite` was ever committed to git history; the live
production commander count and corpus composition.

## What changed (this working tree)

1. **Scraper disabled for EDHREC, Archidekt, Moxfield** — `tools/scrape_decklists/runner.py`.
   - `_throttle()` (every request in the module goes through it) raises `SourceDisabled` for
     `edhrec.com`, `archidekt.com`, `moxfield.com` and their subdomains (`json.edhrec.com`,
     `api2.moxfield.com`, …) before any network call.
   - CLI: `edhrec`, `archidekt`, `moxfield`, `seeds` and `recent --recent-source archidekt` print a
     `[disabled]` message and exit 2 without creating corpus files. `recent` no longer defaults to
     `archidekt`; `--recent-source` must be given.
   - Parse helpers and their tests are kept (no history deleted). `reseed.py` and `PROMPT.md`
     carry a DISABLED banner. New test: `tools/scrape_decklists/tests/test_compliance_block.py`.
2. **Kill switch `DECKDOCTOR_EDHREC_SIGNAL`** — `backend/app/store.py`.
   - Values: `on` (default) / `off` (also `0`, `false`, `no`, `disabled`). Anything else counts as
     `on`, so a typo never changes production.
   - `off` at startup: `edhrec_metrics` is not read into memory (so `/health` and `/admin/reload`
     report `edhrec_commanders: 0`).
   - `off` at any time: `Store.edhrec_for()` returns `{}` for every commander, so every caller
     (`suggest`, `doctor`, `pivot`, `templates`, `upgrade`, `search` ranking) takes its existing
     no-EDHREC path. In `suggest.recommend` that is the `cooccurrence` / `color_staple` tier with
     `w_edh = 0` and no `edhrec` / `edhrec_inclusion` reasons.
   - Tests: `backend/tests/test_edhrec_switch.py` (flag parsing, both modes on a bare Store, the
     load skip, and the live suggester: `on` → tier `edhrec`; `off` → tier `cooccurrence` /
     `color_staple`, non-empty suggestions, no EDHREC reason or detail text).
3. **UI honesty** — `frontend/src/components/reason/reasonText.ts`, `ReasonLine.tsx`.
   - `hasSignalEvidence()`: an `edhrec` / `edhrec_inclusion` reason counts only with a positive
     value. `rankReasons()` drops the rest, so no "EDHREC" chip renders for an absent signal
     (this also covers `RailRow`, which uses `rankReasons`). If such a reason ever leads,
     the sentence is "No inclusion data for <commander>." instead of an EDHREC claim.
   - With the switch off the backend sends no EDHREC reasons at all, so no EDHREC chip appears.
4. **Docs** — `README.md` (compliance note + credits at the top; scraper section and rebuild steps
   no longer instruct EDHREC/Archidekt/Moxfield scraping), `NEXT_SESSION.md` (stop notice; old
   scrape tasks marked historical/cancelled), `deploy/README.md`, `deploy/frontload_scrape.sh`
   (Archidekt walk and EDHREC `seeds` step removed).
5. **Draft permission email** — `docs/public/edhrec-permission-email-draft.md`. **Not sent.**

Verification run on legion (2026-11-24): `tools/scrape_decklists` tests 30 passed;
`backend/tests/test_edhrec_switch.py` 21 passed; `backend/tests/test_suggest.py` 15 passed;
`frontend: npx tsc --noEmit` clean; `tests/ui-kit.spec.ts` 42 passed / 27 skipped.

## How to flip the switch in production (simtrack)

The API runs as `deckdoctor-api.service`, which already loads
`EnvironmentFile=/etc/deck-doctor/secrets.env` (root 0600). **Do not open, cat or print that
file.** The cleanest way is a systemd drop-in, which keeps the flag out of the secrets file:

```bash
# 1. Deploy a build that contains this change first (deploy.sh <ref>); the flag is a no-op before.
# 2. Add the flag as a drop-in (creates /etc/systemd/system/deckdoctor-api.service.d/override.conf):
sudo systemctl edit deckdoctor-api
#    in the editor, add exactly:
#      [Service]
#      Environment=DECKDOCTOR_EDHREC_SIGNAL=off
sudo systemctl restart deckdoctor-api
# 3. Check without printing any secret:
systemctl show deckdoctor-api -p Environment | grep -c 'DECKDOCTOR_EDHREC_SIGNAL=off'   # expect 1
curl -s http://127.0.0.1:8002/health | jq '.edhrec_commanders'                         # expect 0
```

Alternative (same effect): append one line to the EnvironmentFile **without reading it**:
`echo 'DECKDOCTOR_EDHREC_SIGNAL=off' | sudo tee -a /etc/deck-doctor/secrets.env >/dev/null`, then
restart `deckdoctor-api`. Rollback: remove the line / drop-in (`sudo systemctl revert
deckdoctor-api` removes all drop-ins for the unit), restart.

`deploy/DEPLOY.md` is owned by another workstream; add the flag to its environment table when
that file is next edited.

The switch does **not** stop the nightly `deckdoctor-refresh` job from *trying* EDHREC/Archidekt:
once deployed, `runner.py` refuses them and `refresh_corpus.sh` logs "FAILED (continuing)" per
source (it is best-effort, `set -uo pipefail` without `-e`). See open question 3.

## What the ranking loses with the switch off (measured)

Harness: `scoring/eval_suggest.py` functions (`load_decks`, `run_eval`) driven by a scratch
script, against the local `deckdoctor_test` DB copy and local `data/decks.sqlite` (5,263 decks,
354 EDHREC commanders in the store). Hold out 10 cards, limit 50, `test` split, first 300 eligible
decks. Leakage caveat applies (the tables were built from these decks): **use for relative
comparison only.** Production numbers: UNKNOWN (production has a larger corpus).

| Decks (test split) | Switch | n | recall@10 | recall@25 | recall@50 | MRR | popularity baseline r@25 / MRR |
|---|---|---:|---:|---:|---:|---:|---|
| mixed (first 300) | on  | 300 | 0.093 | 0.167 | 0.240 | 0.043 | 0.072 / 0.032 |
| mixed (first 300) | off | 300 | 0.034 | 0.075 | 0.143 | 0.020 | 0.072 / 0.032 |
| commander has EDHREC rows | on  | 300 | 0.194 | 0.308 | 0.408 | 0.085 | 0.087 / 0.035 |
| commander has EDHREC rows | off | 300 | 0.039 | 0.083 | 0.160 | 0.024 | 0.087 / 0.035 |
| commander without EDHREC rows | on/off (identical) | 271 | 0.027 | 0.069 | 0.124 | 0.015 | 0.074 / 0.034 |

Reading: for commanders EDHREC covers, recall@25 falls from 0.31 to 0.08 (about −73 %) and MRR
from 0.085 to 0.024. With the switch off, the current co-occurrence/staple tier is at or **below
the popularity baseline** (r@25 0.083 vs 0.087; MRR 0.024 vs 0.035). Commanders without EDHREC rows
were already there. The cold-start tier needs work regardless of EDHREC (e.g. blend in the
popularity/staple ranking it currently loses to).

## What the switch does not remove

- **Offline fused synergy:** `scoring/build_cooccurrence.py` folds EDHREC synergy into
  `card_relationships.synergy_ab/ba` via `fuse()` (`BETA = 0.4`). Those rows stay until a rebuild
  with an empty `edhrec_metrics` source (a missing file errors; use an empty table).
- **The deck corpus itself:** local `data/decks.sqlite` is `archidekt` 2,895 + `moxfield` 2,358 +
  `sample` 10 decks — all collected via the now-disabled paths (Archidekt API and EDHREC
  deckpreview). Co-occurrence, staples and commander popularity are mined from it. Production's
  corpus composition: UNKNOWN (query `SELECT source, count(*) FROM corpus_decks GROUP BY 1` there).
- **Stored copies:** `data/edhrec.sqlite`, `data/decklists/edhrec-*.jsonl`,
  `tools/scrape_decklists/*.log` on legion and simtrack, and the Postgres `edhrec_metrics` table.
  They are gitignored, but the two real-response fixtures
  `tools/scrape_decklists/tests/fixtures/edhrec_deckpreview_27071260.json` and
  `archidekt_deck_27077380.json` **are tracked** in the public repo.
- **Other UI copy outside `components/reason/`** (not in this change's ownership):
  `SuggestTab.tsx` tier blurb ("no EDHREC page for this commander" — wrong reason when the switch
  is off), `SuggestionsPanel.tsx` footer ("blended from EDHREC, …" shown regardless of tier),
  `PivotTab.tsx` / `lib/pivot.ts` EDHREC wording, `TuneUpTab.tsx`, `UpgradeSweepPanel.tsx`.
  Recommendation: drive those from the response `tier` / reasons and never print "EDHREC" when
  `tier !== "edhrec"`.

## Recommendations not done here (files owned elsewhere)

- **Attribution:** no footer or credits element exists in `frontend/src/components/reason/` or the
  page shell, so none was added. Recommend a small credits line in the app footer (e.g.
  `DoctorRail.tsx`'s `<footer>` or the layout): "Card data and images: Scryfall
  (https://scryfall.com). Combos: Commander Spellbook (https://commanderspellbook.com)", and make the
  existing "Commander Spellbook" text in `CombosTab.tsx` / `DeckCombosPanel.tsx` a link. README now
  carries the same credits.
- `deploy/refresh_corpus.sh`: drop `archidekt` from `RECENT_SOURCES` and remove the `seeds` pass;
  pass an empty `edhrec_metrics` source to `build_cooccurrence.py`.
- `tools/refresh_loop.py` (dev): its `--recent-source` only offers `archidekt|moxfield` and its
  scrape step now exits 2, which makes the loop skip the rest of the cycle. Retire or rewire.
- `deploy/DEPLOY.md`: document `DECKDOCTOR_EDHREC_SIGNAL` in the environment table.
- Replace the two tracked real-response fixtures with hand-written ones.
- Switch `tools/import_spellbook/runner.py` to the bulk `variants.json.gz` export (research §5.2).

## Open questions (owner decisions)

1. When to set `DECKDOCTOR_EDHREC_SIGNAL=off` in production (measured cost above), and whether to
   send the permission email first.
2. If EDHREC says no: delete `edhrec_metrics` (Postgres + `data/edhrec.sqlite`), rebuild fused
   synergy without it, and decide whether to purge history. Whether anything EDHREC-derived is in
   git history: UNKNOWN (not checked).
3. Archidekt/Moxfield-sourced decklists: keep, delete, or ask those sites? Their terms do not
   permit collection as far as fetched; Moxfield's are UNKNOWN.
4. TappedOut / Deckstats / AetherHub / ManaStack: the nightly refresh still walks them; their terms
   are UNKNOWN. Pause them until checked?
   *(2026-11-25 update: TappedOut gave provisional verbal permission — John Smith, Investor
   Relations, phone call, email confirmation pending — so it stays enabled at 1 request / 30 s;
   see `docs/permissions/tappedout-2026-11-25.md`. Deckstats / AetherHub / ManaStack remain
   UNKNOWN.)*
5. A lawful corpus going forward (user-submitted decks with an aggregation notice — the notice does
   not exist yet).
6. Whether Deck Doctor (free, optional Patreon for a score breakdown, affiliate links) is
   "commercial" under EDHREC's Terms: UNKNOWN; a question for EDHREC or counsel.

## Re-enabling a site after written permission

No code edit is needed. Save the permission (email or terms page) under `docs/permissions/`, then add a grant to `tools/scrape_decklists/permissions.json`:

```json
{"grants": [{
  "host": "edhrec.com",
  "granted_by": "name or role at the site",
  "date": "YYYY-MM-DD",
  "evidence": "docs/permissions/edhrec-2026-12-01.md",
  "allowed_path_prefixes": ["/pages/"],
  "min_interval_s": 5,
  "user_agent": "string they asked for"
}]}
```

- Required: `host`, `granted_by`, `date`, `evidence`. A grant missing any is ignored (fail closed), as is a missing or corrupt file.
- Optional: `allowed_path_prefixes` limits requests to those paths (anything else raises `SourceDisabled`); `min_interval_s` can only slow us down; `user_agent` is sent when they ask for one.
- A grant on `edhrec.com` covers its subdomains (`json.edhrec.com`).
- Nightly refresh: set `EXTRA_RECENT_SOURCES="archidekt"` and/or `ENABLE_SEEDS=1` in the refresh unit. The runner still refuses a source whose host has no grant.
- `DECKDOCTOR_SCRAPE_PERMISSIONS` can point at another grants file (used by tests).
- Permission to scrape does not change `DECKDOCTOR_EDHREC_SIGNAL`; that switch is separate.
