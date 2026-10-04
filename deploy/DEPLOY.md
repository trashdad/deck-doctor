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
| Secrets | `DATABASE_URL` in the api/refresh/backup units, `SIMMANDER_JWT_SECRET` in `deckdoctor-api.service.d/jwt.conf`, restic env in `/etc/deck-doctor/restic.env` (root 0400). Never commit or print them. |
| Unit backups | `/var/backups/deck-doctor/` (copies of units before they were edited) |

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
3. Units: copy `deploy/systemd/*` to `/etc/systemd/system/`, fill in `DATABASE_URL`, add the JWT
   drop-in (`[Service] Environment=SIMMANDER_JWT_SECRET=<tracker [auth] secret_key>`), then
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

Combo catalogs: `build_relationships` only produces *asserted* combos when `COMBO_CATALOG` /
`KNOWN_COMBOS` point at the simmander repo's `data/combo_catalog.json` + `data/known_combos.json`.
The VPS has none, so prod has **0 asserted combos** (Commander Spellbook's 88k combos are
unaffected). With the catalogs a staging rebuild produced 96, and the golden scoring tests +
`test_engine_completion_surfaces_missing_piece` pass only on such data. Owner decision pending.

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
`deckdoctor_verify`; run uvicorn on 127.0.0.1:8012 and the web release on :3011; run
`backend`/`scoring` pytest there (the conftest only allows destructive tests against a local or
`*_test` DB — on simtrack *prod is local too*, so double-check `DATABASE_URL` before running
pytest). Drop the DB, role and directory afterwards.

## Alternative: containers

`deploy/compose.yaml` + the Dockerfiles run the full stack (see `deploy/README.md`). Production
does not use them.
