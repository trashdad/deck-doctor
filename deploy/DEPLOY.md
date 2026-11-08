# Deploying Deck Doctor at simmander.app/deck-doctor

Deck Doctor is path-hosted **alongside** the price tracker on the tracker VPS (**simtrack**).
The tracker keeps serving `/`; Deck Doctor serves `/deck-doctor`.

```
simmander.app/                -> tracker            (not ours — don't touch)
simmander.app/deck-doctor      -> deckdoctor-web     Next.js standalone, 127.0.0.1:3001
simmander.app/deck-doctor/api  -> deckdoctor-api     FastAPI/uvicorn,     127.0.0.1:8002
```

**The nginx blocks live in the tracker repo** (`simmander-tracker/nginx/nginx.conf`, applied by
the tracker's auto-deploy). They already route the paths above and return **403 for
`/deck-doctor/api/admin/`**. `deploy/nginx-deckdoctor.conf` here is reference only.

## Production layout (simtrack, as of 2026-10-04)

| Thing | Where |
|---|---|
| SSH | `ssh trashdad@simtrack` (Tailscale SSH, passwordless `sudo -n`). Run remote commands from `cd /tmp`. |
| Checkout | `/opt/deck-doctor` (owner `simmander`, **detached HEAD** at the deployed sha). Run git as the owner: `sudo -u simmander git -C /opt/deck-doctor …` (as trashdad it fails with "dubious ownership"). |
| Python | `/opt/deck-doctor/.venv` (Python 3.10) |
| Web releases | `/opt/deck-doctor/releases/web-<sha>-<ts>/` (standalone server + `.next/static` + `public/`); `releases/current` → the live one |
| Database | Postgres 14 on the box, DB `deckdoctor` (role `deckdoctor`). ~85.6k corpus decks. |
| Units | `deckdoctor-api`, `deckdoctor-web`, `deckdoctor-refresh.timer` (04:30 UTC), `deckdoctor-backup.timer` (03:30 UTC) |
| Secrets | `/etc/deck-doctor/secrets.env` (root 0600: `DATABASE_URL`, `SIMMANDER_JWT_SECRET`) via `EnvironmentFile=` in api/refresh/backup; `/etc/deck-doctor/restic.env` (root 0400). Unit files hold **no** secrets. Never commit, cat or echo them. |
| Alerts | `OnFailure=simmander-alert@%n.service` on all four units → the tracker's pager (ntfy topic `simmander-watchdog`) |
| Combo catalogs | `/var/lib/deck-doctor/combo-catalogs/{combo_catalog.json,known_combos.json}` (root:simmander 0640), from the simmander repo |
| Unit backups | `/var/backups/deck-doctor/` (root 0700; copies of units before they were edited) |

## Deploy (the normal path)

Pushing to `main` does **not** deploy. On simtrack:

```bash
cd /tmp
sudo /opt/deck-doctor/deploy/deploy.sh            # deploy origin/main
sudo /opt/deck-doctor/deploy/deploy.sh <ref>      # a branch / tag / sha
sudo /opt/deck-doctor/deploy/deploy.sh --force    # rebuild + reinstall even if already there
```

What it does (`deploy/deploy.sh`):
1. refuses if another deploy holds the lock or **`deckdoctor-refresh` is running**;
2. `git fetch` + **detached checkout** of the ref (as `simmander`);
3. `pip install -r backend/requirements.txt` — only if it changed;
4. `npm ci` — only if `package*.json` changed; then `next build`;
5. assembles an **immutable release**: copies `.next/standalone`, `.next/static` and `public/`
   into `releases/web-<sha>-<ts>/` and flips `releases/current` (atomic `mv -T`). `next build`
   wipes `frontend/.next`, so the web unit must never serve from there;
6. restarts `deckdoctor-api` + `deckdoctor-web` and health-checks `http://127.0.0.1:8002/health`,
   `http://127.0.0.1:3001/deck-doctor`, one hashed `_next/static` chunk and `golden-axe.svg`;
7. **on any failure after the checkout, rolls back**: previous commit + previous release (no
   rebuild), restart, re-check, exit 1. Keeps the newest 3 releases (+ current and previous).

Typical run: ~45 s with `npm ci`, ~30 s without; the API is unavailable for ~5–10 s while it
reloads its in-memory store. Manual rollback to any earlier commit = `deploy.sh <old-sha>`.

Then verify from outside:
```bash
curl -s  https://simmander.app/deck-doctor/api/health        # 200, card/EDHREC/spellbook counts
curl -sI https://simmander.app/deck-doctor                    # 200
curl -sI https://simmander.app/deck-doctor/golden-axe.svg     # 200 (public/ is in the release)
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://simmander.app/deck-doctor/api/admin/reload  # 403
# on simtrack: the nightly refresh's reload path (loopback, no proxy headers) must still work
curl -s -X POST http://127.0.0.1:8002/admin/reload            # 200
```
Cloudflare blocks default script user-agents (`error code: 1010`); send a browser-like UA
when scripting against the public URL.

## Secrets

Since 2026-10-05 no unit file contains a secret. `deckdoctor-api`, `-refresh` and `-backup` read
`EnvironmentFile=/etc/deck-doctor/secrets.env` (systemd reads it as root before dropping to
`simmander`; the web unit needs no secrets). Format — single-quote values so systemd takes them
literally:

```
DATABASE_URL='postgresql://deckdoctor:<password>@127.0.0.1:5432/deckdoctor'
SIMMANDER_JWT_SECRET='<the tracker backend/config.ini [auth] secret_key>'
```

Check without revealing: `sudo test -s /etc/deck-doctor/secrets.env && sudo grep -c '^[A-Z_]*=' /etc/deck-doctor/secrets.env`
(→ 2) and `systemctl show deckdoctor-api -p Environment` (must not list either variable). After
editing: `sudo systemctl restart deckdoctor-api` (refresh/backup pick it up on their next run).

## Failure alerts

All four units carry `OnFailure=simmander-alert@%n.service` — the tracker's generic unit-failure
pager (`simmander-tracker/docs/systemd/simmander-alert@.service` → `backend.healing.notify`): ntfy
topic `simmander-watchdog` always, plus Discord/Telegram/email unless muted, throttled to one
page per unit per hour. Tested 2026-10-05 with a throwaway failing unit (`ntfy=ok`). The handler
runs as `simmander`, which cannot read other units' journals, so the page may say "(no output
captured)" — look with `sudo journalctl -u <unit>`. If the tracker ever drops that template,
systemd only logs a missing OnFailure= target; the units themselves are unaffected.

## First-time setup on a new box

1. Node 20, Python 3.10+, Postgres. `git clone https://github.com/trashdad/deck-doctor /opt/deck-doctor`
   (owner `simmander`), `python3 -m venv /opt/deck-doctor/.venv`,
   `.venv/bin/pip install -r backend/requirements.txt`.
2. Database: `CREATE ROLE deckdoctor LOGIN PASSWORD '…'; CREATE DATABASE deckdoctor OWNER deckdoctor;`
   then either restore a dump (same PG major or newer target:
   `pg_restore --no-owner --clean --if-exists -d deckdoctor <dump>`) or rsync the SQLite build
   artifacts into `data/` and run `tools/load_to_postgres.py --database-url …`.
   ⚠️ `load_to_postgres.py` defaults to `postgresql://deckdoctor:deckdoctor@localhost/deckdoctor`
   when `DATABASE_URL` is unset — always pass the URL explicitly on a box that hosts prod.
3. Units: copy `deploy/systemd/*` to `/etc/systemd/system/`, create `/etc/deck-doctor/secrets.env`
   (see Secrets) and the combo catalogs (see below), then
   bootstrap `releases/current` once (build the frontend, then
   `cp -a frontend/.next/standalone releases/web-init && cp -a frontend/.next/static releases/web-init/.next/static && cp -a frontend/public releases/web-init/public && ln -s web-init releases/current`),
   `systemctl daemon-reload && systemctl enable --now deckdoctor-api deckdoctor-web deckdoctor-refresh.timer deckdoctor-backup.timer`.
   After that, always use `deploy.sh`.
4. nginx: add the blocks from `deploy/nginx-deckdoctor.conf` to the tracker's server block **via
   the tracker repo** (`nginx/nginx.conf`).

## Nightly data refresh (`deckdoctor-refresh`, 04:30 UTC)

`deploy/refresh_corpus.sh`: scrape (newest-first per source + a commander-breadth pass) →
`load_corpus` → `build_relationships` → `build_cooccurrence` → `load_to_postgres` →
`POST localhost:8002/admin/reload` (allowed: loopback, no proxy headers). Logs:
`journalctl -u deckdoctor-refresh`. It runs code from `/opt/deck-doctor`, which is why deploys
refuse to run while it is active.

### Combo catalogs

`build_relationships` only produces *asserted* combos (`engines.asserted_combo`, the
`card_relationships.combo` axis) when the refresh unit's `COMBO_CATALOG` / `KNOWN_COMBOS` point at
the catalogs. They are **shared data owned by the simmander repo** (`data/combo_catalog.json`,
`data/known_combos.json`; the hub will later own the contract) and are copied to
`/var/lib/deck-doctor/combo-catalogs/` (root:simmander 0640). Refresh them by hand when the
simmander repo changes them:

```bash
scp C:/simmander/simmander/data/{combo_catalog.json,known_combos.json} trashdad@simtrack:/tmp/
ssh trashdad@simtrack 'cd /tmp && for f in combo_catalog.json known_combos.json; do sudo install -m 640 -o root -g simmander /tmp/$f /var/lib/deck-doctor/combo-catalogs/$f; rm /tmp/$f; done'
```

From June to 2026-10-05 the VPS had none, so prod had 0 asserted combos (Commander Spellbook's
88k combos were unaffected). A missing configured catalog is now logged as a WARNING by
`refresh_corpus.sh`.

## Adding new card sets (card data refresh, run on legion)

The nightly refresh only rebuilds deck-driven tables. New cards need the card layer
rebuilt on the dev box and shipped. Done this way on 2026-10-05 (5 sets, +1,148 cards):

1. Scryfall now publishes bulk data as gzipped JSONL (`jsonl_download_uri` on
   `https://api.scryfall.com/bulk-data/default-cards`). Convert it to the JSON array
   `prep_cards.py` reads, e.g. `C:/simmander/simmander/data/default-cards.<date>.json`.
2. `python scoring/prep_cards.py --src <that file> --out data/cards.json --keep-ids-from data/cards.json`
   — `--keep-ids-from` keeps every existing card's print (and id) while it still exists;
   without it, reprints in new sets change ids that user decks store.
3. `python backend/scripts/enrich_lands.py` (rewrites `backend/data/land_meta.json`).
4. Fetch the MTGish rules data at a pinned upstream (github.com/i5jb/mtgish) commit and
   record its hash (the card layer reads upstream directly; `mtgish_schema.py` handles the
   2026-10 schema — folded `PutCounters`/`Exile`/... ops, `Reflexive_*` actions, `_Trigger If`,
   `AnchorWord`):
   ```bash
   SHA=<i5jb/mtgish commit>
   curl -sSL -o data/mtgish.lines.$SHA.json https://raw.githubusercontent.com/i5jb/mtgish/$SHA/data/mtgish.lines.json
   sha256sum data/mtgish.lines.$SHA.json
   ```
   (`scoring/mtgish_merge.py` — April-2026 base plus upstream gap-fill — is only needed to
   reproduce stores built before the port.)
5. Fresh store: `build_store.py --cards data/cards.json --out <new>`, then
   `build_semantics.py` and `build_fingerprints.py` with `--db <new> --mtgish data/mtgish.lines.$SHA.json`.
6. Verify against the previous store: diff `card_flat_tags` / `card_fingerprints` per card and
   explain every lost tag (upstream re-parses change cards between commits; the unmapped-operator
   list `build_fingerprints.py` prints shows new upstream ops), then rehearse `build_relationships` →
   `build_cooccurrence` → `load_to_postgres` into `deckdoctor_test` and run both test suites.
7. Ship: back up prod, copy the new store over `/opt/deck-doctor/data/scores.sqlite`, run
   `deckdoctor-refresh` (rebuilds relationships/co-occurrence, loads Postgres, reloads the API),
   then deploy the commit that carries `data/cards.json` + `land_meta.json`.

## Backups (`deckdoctor-backup`, 03:30 UTC)

`deploy/backup.sh` (runs as root) writes two independent copies; the unit fails if either fails:

| Copy | How | Retention |
|---|---|---|
| **tower** (on-site NAS) `root@tower:/mnt/user/backups/deck-doctor/` | `tools/backup_db.py` as `simmander` (its SSH key is authorized on tower): `pg_dump -Fc` → scp, host-tagged file names | newest 14 per host (pruned by the script) |
| **callisto** (off-site) restic repo `rest:http://…@callisto:8000/simmander/deck-doctor` | `pg_dump -Fc -Z0` as `postgres` (peer auth) streamed by `restic backup --stdin-from-command` (a failed dump never becomes a snapshot); tags `pg nightly`, host `simtrack` | append-only rest-server: **no forget/prune from simtrack** — prune on callisto |

`/etc/deck-doctor/restic.env` (root 0400) reuses the tracker's rest-server user and repo password
file (`/etc/restic/repo-password`) with its own repo path, so the one password the owner already
keeps for the tracker also opens Deck Doctor's repo.

Run one now / inspect:
```bash
sudo systemctl start deckdoctor-backup && journalctl -u deckdoctor-backup -n 30
sudo bash -c 'set -a; . /etc/deck-doctor/restic.env; set +a; restic snapshots'
sudo -u simmander ssh root@tower ls -la /mnt/user/backups/deck-doctor/
```
Restore:
```bash
# from tower
pg_restore --no-owner --clean --if-exists -d deckdoctor deckdoctor-<host>-<ts>.dump
# from callisto
sudo bash -c 'set -a; . /etc/deck-doctor/restic.env; set +a; restic dump latest /deckdoctor.dump' > deckdoctor.dump
pg_restore --no-owner --clean --if-exists -d deckdoctor deckdoctor.dump
```
History: the job failed on Postgres password auth from June until 2026-10-04, so tower only holds
two June dumps plus the October ones.

## Staging (how 2026-10-04's release was verified)

Copy prod data into a throwaway DB and run the candidate on spare loopback ports:
`pg_dump -Fc deckdoctor` → `createdb deckdoctor_verify` (own temp role) → `pg_restore`; check out
the candidate in `/opt/deck-doctor-staging` with a `.env` pointing `DATABASE_URL` at
`deckdoctor_verify`; run uvicorn on 127.0.0.1:8012 and the web release on :3011. For pytest use a
DB whose name ends in **`_test`** (e.g. `deckdoctor_test`, restored from the same dump): the
conftest guard refuses anything else, and always refuses `deckdoctor` (prod is local on simtrack)
unless `DECKDOCTOR_ALLOW_DESTRUCTIVE_TESTS=1` — never set that on simtrack. Drop the DBs, role and
directory afterwards.

## Alternative: containers

`deploy/compose.yaml` + the Dockerfiles run the full stack (see `deploy/README.md`). Production
does not use them.
