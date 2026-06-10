# Deploying Deck Doctor at simmander.app/deckdoctor

Deck Doctor is path-hosted **alongside** the price tracker on the same VPS — it does
**not** replace simmander.app. The tracker keeps serving `/`; Deck Doctor serves
`/deckdoctor`. Two small services + three nginx location blocks; the tracker is untouched.

```
simmander.app/               -> tracker  (Vite static, FastAPI :8000)   [unchanged]
simmander.app/deckdoctor     -> Deck Doctor web  (Next.js standalone :3001)
simmander.app/deckdoctor/api -> Deck Doctor API  (FastAPI :8002)
```

## 0. Prerequisites on the box
- Node 20+ and a Python 3.13 venv (`/opt/deck-doctor/.venv`).
- The repo cloned to `/opt/deck-doctor` (origin: the `deck-doctor` GitHub repo).
- Ports **8002** (API) and **3001** (web) free — the tracker uses 8000.

## 1. Backend
```bash
cd /opt/deck-doctor/backend
/opt/deck-doctor/.venv/bin/pip install -r requirements.txt   # fastapi, uvicorn, pydantic, python-dotenv
```

## 2. Data (the one heavy step)
The API reads `data/cards.json` (committed, ~21 MB) plus several SQLite stores that are
**gitignored and must be present on the box**:
`scores.sqlite` (~292 MB), `edhrec.sqlite`, `decks.sqlite`, `spellbook.sqlite`.
Two ways to get them there:

- **Ship the prebuilt stores (fastest):** rsync them from a machine that already built them:
  ```bash
  rsync -avz data/{scores.sqlite,edhrec.sqlite,decks.sqlite,spellbook.sqlite} \
        simmander@VPS:/opt/deck-doctor/data/
  ```
- **Or rebuild on the box** (needs the scraped corpus + sibling combo catalogs):
  ```bash
  python tools/scrape_decklists/load_corpus.py
  python scoring/build_relationships.py --db data/scores.sqlite \
    --catalog ../simmander/data/combo_catalog.json --catalog ../simmander/data/known_combos.json
  python scoring/build_cooccurrence.py --scores data/scores.sqlite \
    --decks data/decks.sqlite --edhrec data/edhrec.sqlite --min-support 20
  python tools/import_spellbook/load_spellbook.py   # spellbook.sqlite
  ```
`userdecks.sqlite` is created automatically on first write.

## 3. Frontend (build with the path prefix)
`basePath=/deckdoctor` is the default; nothing to set.
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
curl -s localhost:3001/deckdoctor    # Next HTML
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
curl -s https://simmander.app/deckdoctor/api/health
curl -sI https://simmander.app/deckdoctor          # 200, Next HTML
```
Open https://simmander.app/deckdoctor — commander list (popularity), Template dropdown,
and the Doctor should all work; the tracker at https://simmander.app/ is unaffected.

## 7. Auto-deploy (optional)
Mirror the tracker's `auto-deploy` timer for `/opt/deck-doctor`: `git pull`, rebuild
frontend, `pip install -r`, `systemctl restart deckdoctor-api deckdoctor-web`. Keep the
heavy data rebuild on its own cadence (`tools/refresh_loop.py`), not every deploy.
