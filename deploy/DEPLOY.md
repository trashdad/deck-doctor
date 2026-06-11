# Deploying Deck Doctor at simmander.app/deck-doctor

Deck Doctor is path-hosted **alongside** the price tracker on the same VPS — it does
**not** replace simmander.app. The tracker keeps serving `/`; Deck Doctor serves
`/deck-doctor`. Two small services + three nginx location blocks; the tracker is untouched.

```
simmander.app/               -> tracker  (Vite static, FastAPI :8000)   [unchanged]
simmander.app/deck-doctor     -> Deck Doctor web  (Next.js standalone :3001)
simmander.app/deck-doctor/api -> Deck Doctor API  (FastAPI :8002)
```

## 0. Prerequisites on the box
- Node 20+ and a Python 3.13+ venv (`/opt/deck-doctor/.venv`).
- The repo cloned to `/opt/deck-doctor` (origin: the `deck-doctor` GitHub repo).
- **Postgres 16** (the tracker already runs it) — Deck Doctor gets its **own
  database** on that server, isolated from the tracker.
- Ports **8002** (API) and **3001** (web) free — the tracker uses 8000.

## 1. Backend
```bash
cd /opt/deck-doctor/backend
/opt/deck-doctor/.venv/bin/pip install -r requirements.txt   # incl. psycopg2-binary
```

## 2. Database (its own deckdoctor DB on the shared Postgres)
Create an isolated role + database (one line; separate from the tracker's DB):
```bash
sudo -u postgres psql -c "CREATE ROLE deckdoctor LOGIN PASSWORD 'STRONG_PW';"
sudo -u postgres psql -c "CREATE DATABASE deckdoctor OWNER deckdoctor;"
export DATABASE_URL=postgresql://deckdoctor:STRONG_PW@127.0.0.1:5432/deckdoctor
```
Put the same `DATABASE_URL` in `deploy/systemd/deckdoctor-api.service`.

The app reads `data/cards.json` (committed, ~21 MB) and **Postgres** for everything
else. The analytical tables are loaded into Postgres from the offline SQLite build
artifacts (gitignored, regenerable). Two ways to populate the DB:

- **Ship a dump (fastest, dev→prod):** on a machine that already built + loaded the
  data, `pg_dump` it; restore on the box:
  ```bash
  # on dev:
  pg_dump --no-owner --no-acl -Fc deckdoctor > deckdoctor.dump
  rsync -avz deckdoctor.dump simmander@VPS:/tmp/
  # on the box:
  pg_restore --no-owner --clean --if-exists -d deckdoctor /tmp/deckdoctor.dump
  ```
- **Or rsync the SQLite artifacts + load them into PG on the box:**
  ```bash
  rsync -avz data/{scores.sqlite,edhrec.sqlite,decks.sqlite,spellbook.sqlite} \
        simmander@VPS:/opt/deck-doctor/data/
  python tools/load_to_postgres.py        # mirrors the artifacts into Postgres
  ```
- **Or rebuild from scratch** (needs the scraped corpus + sibling combo catalogs),
  then `python tools/load_to_postgres.py`:
  ```bash
  python tools/scrape_decklists/load_corpus.py
  python scoring/build_relationships.py --db data/scores.sqlite \
    --catalog ../simmander/data/combo_catalog.json --catalog ../simmander/data/known_combos.json
  python scoring/build_cooccurrence.py --scores data/scores.sqlite \
    --decks data/decks.sqlite --edhrec data/edhrec.sqlite --min-support 20
  python tools/import_spellbook/load_spellbook.py
  python tools/load_to_postgres.py
  ```
The userdecks tables are created automatically on first write.

## 3. Frontend (build with the path prefix)
`basePath=/deck-doctor` is the default; nothing to set.
```bash
cd /opt/deck-doctor/frontend
npm ci && npm run build
# standalone output needs static + public copied next to server.js:
cp -r .next/static .next/standalone/.next/static
cp -r public        .next/standalone/public   # if present
```

## 4. Services
```bash
sudo cp deploy/systemd/deckdoctor-api.service deploy/systemd/deckdoctor-web.service /etc/systemd/system/
# edit User=/paths if your layout differs from /opt/deck-doctor + user `simmander`
sudo systemctl daemon-reload
sudo systemctl enable --now deckdoctor-api deckdoctor-web
curl -s localhost:8002/health        # {"status":"ok",...}
curl -s localhost:3001/deck-doctor    # Next HTML
```

## 5. nginx
Paste the blocks from `deploy/nginx-deckdoctor.conf` into the tracker's `server { }`
for simmander.app, **above** its `location / {}`. Then:
```bash
sudo nginx -t && sudo systemctl reload nginx
```
No new TLS cert needed — it's the same hostname as the tracker.

## 6. Verify live
```bash
curl -s https://simmander.app/deck-doctor/api/health
curl -sI https://simmander.app/deck-doctor          # 200, Next HTML
```
Open https://simmander.app/deck-doctor — commander list (popularity), Template dropdown,
and the Doctor should all work; the tracker at https://simmander.app/ is unaffected.

## 7. Backups (to the tower NAS)
`tools/backup_db.py` runs `pg_dump -Fc` and scp's the dump to tower, keeping the
newest N (default 14). It needs the deploy user's SSH key authorized on tower
(Tailscale-reachable). One-off:
```bash
python tools/backup_db.py --dest root@tower:/mnt/user/backups/deck-doctor --keep 14
```
Schedule it daily:
- **Prod (VPS):** install the systemd timer:
  ```bash
  sudo cp deploy/systemd/deckdoctor-backup.{service,timer} /etc/systemd/system/
  sudo systemctl daemon-reload && sudo systemctl enable --now deckdoctor-backup.timer
  ```
- **Dev (Windows):** a Daily Task Scheduler job named `DeckDoctorDBBackup` runs it
  at 03:30 (created with `schtasks`; the dev box must be on at that time).

Restore: `pg_restore --no-owner --clean --if-exists -d deckdoctor <dump>`.

## 8. Auto-deploy (optional)
Mirror the tracker's `auto-deploy` timer for `/opt/deck-doctor`: `git pull`, rebuild
frontend, `pip install -r`, `systemctl restart deckdoctor-api deckdoctor-web`. Keep the
heavy data rebuild on its own cadence (`tools/refresh_loop.py`), not every deploy.
