# Shared Login + User-Scoped Decks — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a logged-in simmander.app user use the same login on Deck Doctor and own their saved decks.

**Architecture:** The tracker already issues a JWT in the `simmander_session` cookie on domain
`.simmander.app`. Deck Doctor is the same origin (`simmander.app/deck-doctor`), so the browser sends
that cookie to Deck Doctor's API automatically. Deck Doctor's backend validates the JWT with the
**shared secret** (read-only; no tracker-DB access) to identify the user, and scopes saved decks by
`user_id`. Login is an in-app modal that POSTs to the tracker's shared `/api/auth/login`; logout/register
reuse the tracker. The frontend caches the username in localStorage for display.

**Tech Stack:** FastAPI + psycopg2 + PyJWT (backend), Next.js + zustand (frontend), Postgres `deckdoctor` DB.

**Spec:** `docs/superpowers/specs/2026-06-11-shared-login-user-decks-design.md`

**Working dir for all commands:** `C:/simmander/simmander-deckbuilder`. Backend tests run from `backend/`
with the local Postgres (`C:\simmander\pg`) up and `DATABASE_URL` defaulting to
`postgresql://deckdoctor:deckdoctor@localhost:5432/deckdoctor`.

---

## Task 1: Add PyJWT dependency

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add the dependency**

In `backend/requirements.txt`, add `pyjwt>=2.8` after the `psycopg2-binary` line:

```
httpx>=0.27
psycopg2-binary>=2.9
pyjwt>=2.8
pytest>=8.0
python-dotenv>=1.0
```

- [ ] **Step 2: Install it**

Run: `python -m pip install "pyjwt>=2.8"`
Expected: `Successfully installed PyJWT-2.x.x` (or "already satisfied").

- [ ] **Step 3: Verify import**

Run: `python -c "import jwt; print(jwt.__version__)"`
Expected: prints a version ≥ 2.8.

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "build: add PyJWT for shared-session validation"
```

---

## Task 2: JWT config

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add the secret + algorithm**

In `backend/app/config.py`, immediately after the `DATABASE_URL = ...` block, add:

```python
# --- Shared auth (validate the tracker's simmander_session JWT) -------------
# The SAME secret + algorithm the tracker signs its JWTs with (tracker
# backend/config.ini [auth]). In prod this is set from the tracker's secret via
# the systemd unit; the dev default only validates locally-minted test tokens.
SIMMANDER_JWT_SECRET = os.environ.get("SIMMANDER_JWT_SECRET", "dev-insecure-deckdoctor-secret")
SIMMANDER_JWT_ALG = os.environ.get("SIMMANDER_JWT_ALG", "HS256")
```

- [ ] **Step 2: Verify it loads**

Run: `cd backend && python -c "from app import config; print(config.SIMMANDER_JWT_ALG, bool(config.SIMMANDER_JWT_SECRET))"`
Expected: `HS256 True`

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py
git commit -m "feat: JWT secret/alg config for shared-session auth"
```

---

## Task 3: Auth module (validate the session cookie)

**Files:**
- Create: `backend/app/auth.py`
- Create: `backend/tests/test_auth.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_auth.py`:

```python
"""Shared-session JWT validation tests."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from starlette.requests import Request  # noqa: E402

from app import auth, config  # noqa: E402


def _req(cookie: str | None = None, bearer: str | None = None) -> Request:
    headers = []
    if cookie is not None:
        headers.append((b"cookie", f"{auth.COOKIE_NAME}={cookie}".encode()))
    if bearer is not None:
        headers.append((b"authorization", f"Bearer {bearer}".encode()))
    return Request({"type": "http", "headers": headers})


def _token(user_id: int, *, admin: bool = False, exp_delta: int = 3600,
           secret: str | None = None) -> str:
    return jwt.encode(
        {"sub": str(user_id), "admin": admin, "exp": int(time.time()) + exp_delta},
        secret or config.SIMMANDER_JWT_SECRET, algorithm=config.SIMMANDER_JWT_ALG)


def test_valid_cookie_returns_user():
    u = auth.current_user(_req(cookie=_token(42, admin=True)))
    assert u == {"id": 42, "is_admin": True}


def test_valid_bearer_header_returns_user():
    assert auth.current_user(_req(bearer=_token(7)))["id"] == 7


def test_missing_cookie_returns_none():
    assert auth.current_user(_req()) is None


def test_expired_token_returns_none():
    assert auth.current_user(_req(cookie=_token(1, exp_delta=-10))) is None


def test_wrong_secret_returns_none():
    assert auth.current_user(_req(cookie=_token(1, secret="not-the-secret"))) is None


def test_require_user_raises_401_when_anonymous():
    with pytest.raises(HTTPException) as e:
        auth.require_user(_req())
    assert e.value.status_code == 401


def test_require_user_returns_user_when_valid():
    assert auth.require_user(_req(cookie=_token(9)))["id"] == 9
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_auth.py -q`
Expected: FAIL / ERROR — `ModuleNotFoundError: No module named 'app.auth'`.

- [ ] **Step 3: Implement the module**

Create `backend/app/auth.py`:

```python
"""Shared-session auth — validate the tracker's `simmander_session` JWT.

Deck Doctor is served at simmander.app/deck-doctor, the same origin as the tracker,
so the browser sends the tracker's `simmander_session` cookie to /deck-doctor/api/*
automatically. We verify that JWT with the SHARED secret (HS256) to identify the
user — no tracker-DB access. `sub` is the integer user id; `admin` is a bool claim.
"""

from __future__ import annotations

import jwt
from fastapi import HTTPException, Request

from . import config

COOKIE_NAME = "simmander_session"


def _extract_token(request: Request) -> str | None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        return token
    authz = request.headers.get("authorization", "")
    if authz.lower().startswith("bearer "):
        return authz[7:].strip() or None
    return None


def current_user(request: Request) -> dict | None:
    """{"id": int, "is_admin": bool} for a valid session, else None (anonymous)."""
    token = _extract_token(request)
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, config.SIMMANDER_JWT_SECRET, algorithms=[config.SIMMANDER_JWT_ALG])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    try:
        uid = int(sub)
    except (TypeError, ValueError):
        return None
    return {"id": uid, "is_admin": bool(payload.get("admin", False))}


def require_user(request: Request) -> dict:
    """Same as current_user but 401s when anonymous (for protected routes)."""
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="login required")
    return user
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && python -m pytest tests/test_auth.py -q`
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth.py backend/tests/test_auth.py
git commit -m "feat: validate the shared simmander_session JWT (auth.py)"
```

---

## Task 4: User-scope the userdecks store

**Files:**
- Modify: `backend/app/decks.py`

- [ ] **Step 1: Add the user_id column + index on init**

In `backend/app/decks.py`, the `_SCHEMA` string adds the table; after it, extend `UserDecks.__init__`
to add the column idempotently. Replace the existing `__init__`:

```python
class UserDecks:
    def __init__(self) -> None:
        with db.cursor(commit=True) as cur:
            cur.execute(_SCHEMA)
            cur.execute("ALTER TABLE decks ADD COLUMN IF NOT EXISTS user_id INTEGER")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_decks_user ON decks(user_id)")
```

- [ ] **Step 2: Scope every read/write by user_id**

Replace the `reads` and `writes` method bodies so each takes `user_id`:

```python
    # ---- reads -----------------------------------------------------------
    def list_decks(self, user_id: int) -> list[dict]:
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT d.id, d.name, d.commander_id, d.updated_at,
                       COALESCE(SUM(c.quantity), 0) AS card_count
                FROM decks d
                LEFT JOIN deck_cards c ON c.deck_id = d.id
                WHERE d.user_id = %s
                GROUP BY d.id
                ORDER BY d.updated_at DESC
                """,
                (user_id,))
            rows = cur.fetchall()
        return [
            {"id": r[0], "name": r[1], "commander_id": r[2],
             "updated_at": r[3], "card_count": int(r[4])}
            for r in rows
        ]

    def get(self, deck_id: str, user_id: int) -> dict | None:
        with db.cursor() as cur:
            cur.execute(
                "SELECT id, name, commander_id, created_at, updated_at "
                "FROM decks WHERE id=%s AND user_id=%s", (deck_id, user_id))
            row = cur.fetchone()
            if row is None:
                return None
            cur.execute(
                "SELECT card_id, zone, quantity FROM deck_cards WHERE deck_id=%s",
                (deck_id,))
            cards = cur.fetchall()
        return {
            "id": row[0], "name": row[1], "commander_id": row[2],
            "created_at": row[3], "updated_at": row[4],
            "cards": [{"card_id": c[0], "zone": c[1], "quantity": c[2]} for c in cards],
        }

    # ---- writes ----------------------------------------------------------
    def _write_cards(self, cur, deck_id: str, cards: list[dict]) -> None:
        cur.execute("DELETE FROM deck_cards WHERE deck_id=%s", (deck_id,))
        if cards:
            cur.executemany(
                "INSERT INTO deck_cards (deck_id, card_id, zone, quantity) VALUES (%s,%s,%s,%s)",
                [(deck_id, c.get("id") or c["card_id"], c.get("zone", "Utility"),
                  int(c.get("quantity", 1))) for c in cards])

    def create(self, user_id: int, name: str, commander_id: str | None,
               cards: list[dict]) -> str:
        deck_id = uuid.uuid4().hex
        ts = _now()
        with db.cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO decks (id, user_id, name, commander_id, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (deck_id, user_id, name, commander_id, ts, ts))
            self._write_cards(cur, deck_id, cards)
        return deck_id

    def update(self, deck_id: str, user_id: int, name: str,
               commander_id: str | None, cards: list[dict]) -> bool:
        with db.cursor(commit=True) as cur:
            cur.execute("SELECT 1 FROM decks WHERE id=%s AND user_id=%s", (deck_id, user_id))
            if cur.fetchone() is None:
                return False
            cur.execute(
                "UPDATE decks SET name=%s, commander_id=%s, updated_at=%s "
                "WHERE id=%s AND user_id=%s",
                (name, commander_id, _now(), deck_id, user_id))
            self._write_cards(cur, deck_id, cards)
        return True

    def delete(self, deck_id: str, user_id: int) -> bool:
        with db.cursor(commit=True) as cur:
            cur.execute("DELETE FROM decks WHERE id=%s AND user_id=%s", (deck_id, user_id))
            return cur.rowcount > 0
```

- [ ] **Step 3: Verify it imports**

Run: `cd backend && python -c "from app.decks import get_userdecks; get_userdecks(); print('schema ok')"`
Expected: `schema ok` (the ALTER/CREATE INDEX run without error against the local DB).

- [ ] **Step 4: Commit**

```bash
git add backend/app/decks.py
git commit -m "feat: scope userdecks by user_id (shared-login ownership)"
```

---

## Task 5: Wire the deck routes + /auth/me

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Import auth + Request**

In `backend/app/main.py`, change the FastAPI import line and add the auth import:

```python
from fastapi import FastAPI, HTTPException, Query, Request
```

and near the other local imports (after `from . import db`):

```python
from .auth import current_user, require_user
```

- [ ] **Step 2: Add the /auth/me endpoint**

Immediately after the `@app.post("/admin/reload")` handler block, add:

```python
@app.get("/auth/me")
def auth_me(request: Request) -> dict:
    """Current user from the shared session cookie, or null (anonymous). 200 always."""
    return {"user": current_user(request)}
```

- [ ] **Step 3: Scope every deck route to the current user**

Update the deck routes so each depends on `require_user` and passes `user["id"]`. The `_deck_detail`
helper already takes a deck dict — only the `.get(...)` lookups change. Replace the SP6 deck route block:

```python
@app.get("/decks", response_model=list[DeckSummary])
def decks_list(user: dict = Depends(require_user)) -> list[dict]:
    return get_userdecks().list_decks(user["id"])


@app.post("/decks", response_model=DeckDetail, status_code=201)
def decks_create(req: DeckSave, user: dict = Depends(require_user)) -> dict:
    cards = [e.model_dump() for e in req.cards]
    deck_id = get_userdecks().create(user["id"], req.name, req.commander_id, cards)
    return _deck_detail(get_userdecks().get(deck_id, user["id"]))


@app.post("/decks/import", response_model=ImportResult)
def decks_import(req: ImportRequest, user: dict = Depends(require_user)) -> dict:
    store = get_store()
    cards, unresolved, commander_id = parse_decklist(store, req.text)
    deck_id = get_userdecks().create(user["id"], req.name, commander_id, cards)
    return {"deck": _deck_detail(get_userdecks().get(deck_id, user["id"])),
            "unresolved": unresolved}


@app.get("/decks/{deck_id}", response_model=DeckDetail)
def decks_get(deck_id: str, user: dict = Depends(require_user)) -> dict:
    deck = get_userdecks().get(deck_id, user["id"])
    if deck is None:
        raise HTTPException(404, "deck not found")
    return _deck_detail(deck)


@app.put("/decks/{deck_id}", response_model=DeckDetail)
def decks_update(deck_id: str, req: DeckSave, user: dict = Depends(require_user)) -> dict:
    cards = [e.model_dump() for e in req.cards]
    if not get_userdecks().update(deck_id, user["id"], req.name, req.commander_id, cards):
        raise HTTPException(404, "deck not found")
    return _deck_detail(get_userdecks().get(deck_id, user["id"]))


@app.delete("/decks/{deck_id}", status_code=204)
def decks_delete(deck_id: str, user: dict = Depends(require_user)) -> None:
    if not get_userdecks().delete(deck_id, user["id"]):
        raise HTTPException(404, "deck not found")


@app.get("/decks/{deck_id}/export", response_class=PlainTextResponse)
def decks_export(deck_id: str, user: dict = Depends(require_user)) -> str:
    deck = get_userdecks().get(deck_id, user["id"])
    if deck is None:
        raise HTTPException(404, "deck not found")
    store = get_store()
    by_zone: dict[str, list[tuple[str, int]]] = {}
    for row in deck["cards"]:
        card = store.get(row["card_id"])
        if card is None:
            continue
        by_zone.setdefault(row["zone"], []).append((card["name"], row["quantity"]))
    lines: list[str] = []
    for zone in ZONE_ORDER:
        items = by_zone.get(zone)
        if not items:
            continue
        items.sort(key=lambda t: t[0])
        if zone == "Commanders":
            for name, _qty in items:
                lines.append(f"Commander: {name}")
            lines.append("")
            continue
        lines.append(f"// {export_zone_name(zone)}")
        for name, qty in items:
            lines.append(f"{qty} {name}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
```

Add `Depends` to the fastapi import if not already present:

```python
from fastapi import Depends, FastAPI, HTTPException, Query, Request
```

- [ ] **Step 4: Verify the app imports**

Run: `cd backend && python -c "from app.main import app; print('ok', any(r.path=='/auth/me' for r in app.routes))"`
Expected: `ok True`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: scope deck routes to the session user + add /auth/me"
```

---

## Task 6: Update the deck tests to authenticate

**Files:**
- Modify: `backend/tests/test_decks.py`

- [ ] **Step 1: Add an auth helper + default cookie in the fixture**

In `backend/tests/test_decks.py`, add the imports and a token helper at the top (after the existing
imports), and set a default session cookie on the client in the autouse fixture so the now-protected
routes accept the requests as user 1:

```python
import time
import jwt
from app import config

_USER_A = 1
_USER_B = 2


def _token(user_id: int) -> str:
    return jwt.encode(
        {"sub": str(user_id), "admin": False, "exp": int(time.time()) + 3600},
        config.SIMMANDER_JWT_SECRET, algorithm=config.SIMMANDER_JWT_ALG)


def _as(user_id: int) -> None:
    client.cookies.set("simmander_session", _token(user_id))
```

Then change the `userdecks_tmp` autouse fixture to authenticate as user A by default:

```python
@pytest.fixture(autouse=True)
def userdecks_tmp():
    """Clean userdecks slate per test; authenticated as user A by default."""
    decks_module.get_userdecks.cache_clear()
    decks_module.get_userdecks()            # ensure the schema exists
    with db.cursor(commit=True) as cur:
        cur.execute("TRUNCATE deck_cards, decks RESTART IDENTITY CASCADE")
    _as(_USER_A)
    yield
    client.cookies.clear()
    with db.cursor(commit=True) as cur:
        cur.execute("TRUNCATE deck_cards, decks RESTART IDENTITY CASCADE")
    decks_module.get_userdecks.cache_clear()
```

- [ ] **Step 2: Add cross-user isolation + anonymous tests**

Append these tests to `backend/tests/test_decks.py`:

```python
def test_decks_require_login():
    client.cookies.clear()
    assert client.get("/decks").status_code == 401
    assert client.post("/decks", json={"name": "x", "cards": []}).status_code == 401
    _as(_USER_A)  # restore for any later assertions in this test


def test_user_cannot_see_or_touch_another_users_deck():
    made = client.post("/decks", json={"name": "A's deck", "cards": []}).json()
    deck_id = made["id"]
    _as(_USER_B)
    assert client.get("/decks").json() == []                 # B sees nothing
    assert client.get(f"/decks/{deck_id}").status_code == 404  # B can't read A's
    assert client.delete(f"/decks/{deck_id}").status_code == 404  # B can't delete A's
    _as(_USER_A)
    assert any(d["id"] == deck_id for d in client.get("/decks").json())  # A still has it


def test_auth_me_shapes():
    me = client.get("/auth/me").json()
    assert me["user"]["id"] == _USER_A
    client.cookies.clear()
    assert client.get("/auth/me").json() == {"user": None}
    _as(_USER_A)
```

- [ ] **Step 3: Fix existing tests that call UserDecks methods directly**

Task 4 changed the `UserDecks` method signatures to require `user_id`. Any existing test that calls a
`get_userdecks()` method directly (not via the HTTP client) must pass `_USER_A`. In particular
`test_persistence_across_instances` calls `.get(deck_id)` directly — change it to:

```python
    again = decks_module.get_userdecks().get(deck_id, _USER_A)
```

Search the file for other direct calls and update them the same way (`.create(_USER_A, …)`,
`.update(deck_id, _USER_A, …)`, `.delete(deck_id, _USER_A)`, `.list_decks(_USER_A)`). Tests that go
through `client.post("/decks", …)` etc. need no change — the fixture's cookie authenticates them.

- [ ] **Step 4: Run the full backend suite**

Run: `cd backend && python -m pytest -q`
Expected: all pass (existing deck CRUD/import/export tests now run as authenticated user A via the
fixture cookie; the new auth/isolation tests pass).

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_decks.py
git commit -m "test: deck routes scoped + cross-user isolation + auth/me"
```

---

## Task 7: Frontend — types, API, auth store

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/store/auth.ts`

- [ ] **Step 1: Add the User type**

In `frontend/src/lib/types.ts`, after the `Card` interface, add:

```typescript
export interface User {
  id: number;
  username: string;
}
```

- [ ] **Step 2: Add API calls**

In `frontend/src/lib/api.ts`, add (the tracker auth endpoints live at the domain root `/api`, NOT under
`/deck-doctor/api`; Deck Doctor's own `/auth/me` uses `BASE`):

```typescript
import type { User } from "./types";

const TRACKER_API = "/api"; // simmander.app root — the tracker's shared auth

/** Current user from the shared session, or null. (Deck Doctor's own API.) */
export async function authMe(): Promise<User | null> {
  const res = await fetch(`${BASE}/auth/me`, { credentials: "include" });
  if (!res.ok) return null;
  const data = (await res.json()) as { user: { id: number } | null };
  return data.user ? { id: data.user.id, username: "" } : null;
}

/** Log in via the tracker's shared endpoint (form-encoded). Sets the shared cookie. */
export async function trackerLogin(username: string, password: string): Promise<User> {
  const body = new URLSearchParams({ username, password });
  const res = await fetch(`${TRACKER_API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
    credentials: "include",
  });
  if (!res.ok) throw new Error("Invalid username or password");
  const data = (await res.json()) as { user: { id: number; username: string } };
  return { id: data.user.id, username: data.user.username };
}

export async function trackerLogout(): Promise<void> {
  await fetch(`${TRACKER_API}/auth/logout`, { method: "POST", credentials: "include" }).catch(
    () => {},
  );
}
```

Also add `credentials: "include"` to the existing `get`/`post`/`put`/`del` helpers so the cookie always
rides along. For example the `get` helper becomes:

```typescript
async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { credentials: "include" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}
```

Apply the same `credentials: "include"` addition to `post`, `put`, and `del`.

- [ ] **Step 3: Create the auth store**

Create `frontend/src/store/auth.ts`:

```typescript
import { create } from "zustand";
import { authMe, trackerLogin, trackerLogout } from "@/lib/api";
import type { User } from "@/lib/types";

const USER_KEY = "simmander.user";

function cacheGet(): User | null {
  if (typeof window === "undefined") return null;
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || "null");
  } catch {
    return null;
  }
}

interface AuthState {
  user: User | null;
  ready: boolean;
  refresh: () => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  ready: false,
  // The cookie/JWT is the source of truth for *whether* you're logged in; the
  // username is a cached display name (cleared if it doesn't match the session).
  refresh: async () => {
    const session = await authMe();
    if (!session) {
      localStorage.removeItem(USER_KEY);
      set({ user: null, ready: true });
      return;
    }
    const cached = cacheGet();
    const username = cached && cached.id === session.id ? cached.username : "";
    set({ user: { id: session.id, username }, ready: true });
  },
  login: async (username, password) => {
    const user = await trackerLogin(username, password);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    set({ user });
  },
  logout: async () => {
    await trackerLogout();
    localStorage.removeItem(USER_KEY);
    set({ user: null });
  },
}));
```

- [ ] **Step 4: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts frontend/src/store/auth.ts
git commit -m "feat: frontend auth store + shared-login API calls"
```

---

## Task 8: Frontend — LoginModal + UserMenu

**Files:**
- Create: `frontend/src/components/LoginModal.tsx`
- Create: `frontend/src/components/UserMenu.tsx`

- [ ] **Step 1: Create the LoginModal**

Create `frontend/src/components/LoginModal.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useAuth } from "@/store/auth";

export function LoginModal({ onClose }: { onClose: () => void }) {
  const login = useAuth((s) => s.login);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      onClose();
    } catch {
      setError("Invalid username or password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-[140] bg-black/50" onClick={onClose} />
      <div
        className="fixed left-1/2 top-1/2 z-[145] w-[340px] -translate-x-1/2 -translate-y-1/2
                   rounded-xl border border-edge bg-panel p-5 shadow-2xl"
        data-testid="login-modal"
      >
        <p className="mb-1 font-display text-lg tracking-wide text-accent">Log in</p>
        <p className="mb-4 text-xs text-zinc-500">
          Uses your simmander.app account.
        </p>
        <form onSubmit={submit} className="space-y-3">
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Username or email"
            autoFocus
            className="w-full rounded-md border border-edge bg-ink px-3 py-2 text-sm outline-none focus:border-accent"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            className="w-full rounded-md border border-edge bg-ink px-3 py-2 text-sm outline-none focus:border-accent"
          />
          {error && <p className="text-xs text-red-400">{error}</p>}
          <button
            type="submit"
            disabled={busy || !username || !password}
            data-testid="login-submit"
            className="w-full rounded-lg bg-accent py-2 text-sm font-bold text-ink transition hover:bg-accent/80 disabled:opacity-50"
          >
            {busy ? "Logging in…" : "Log in"}
          </button>
        </form>
        <p className="mt-3 text-center text-[11px] text-zinc-500">
          Need an account?{" "}
          <a href="https://simmander.app" className="text-accent hover:underline">
            Register on simmander.app
          </a>
        </p>
      </div>
    </>
  );
}
```

- [ ] **Step 2: Create the UserMenu**

Create `frontend/src/components/UserMenu.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useAuth } from "@/store/auth";
import { LoginModal } from "./LoginModal";

export function UserMenu() {
  const { user, logout } = useAuth();
  const [showLogin, setShowLogin] = useState(false);

  if (!user) {
    return (
      <>
        <button
          onClick={() => setShowLogin(true)}
          data-testid="open-login"
          className="rounded-lg border border-accent/50 px-3 py-1.5 text-xs font-semibold tracking-wide text-accent transition hover:bg-accent/10"
        >
          Log in
        </button>
        {showLogin && <LoginModal onClose={() => setShowLogin(false)} />}
      </>
    );
  }

  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-zinc-400" data-testid="user-name">
        {user.username || `user #${user.id}`}
      </span>
      <button
        onClick={() => void logout()}
        data-testid="logout"
        className="rounded-lg border border-edge px-2.5 py-1.5 font-semibold text-zinc-400 transition hover:border-accent hover:text-accent"
      >
        Log out
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/LoginModal.tsx frontend/src/components/UserMenu.tsx
git commit -m "feat: in-app login modal + header user menu"
```

---

## Task 9: Frontend — mount the menu, hydrate auth, migrate-on-login, gate saving

**Files:**
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/components/DeckManagerPanel.tsx`

- [ ] **Step 1: Hydrate auth + mount the UserMenu + migrate prompt in page.tsx**

In `frontend/src/app/page.tsx`, add imports:

```tsx
import { UserMenu } from "@/components/UserMenu";
import { useAuth } from "@/store/auth";
import { saveDeck } from "@/lib/api";
```

Inside `Page()`, after the existing hooks, hydrate on mount and track a one-shot migrate prompt:

```tsx
  const { user, ready, refresh } = useAuth();
  const [migratePrompt, setMigratePrompt] = useState(false);
  const prevUser = useRef<number | null>(null);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // When the user transitions anonymous -> logged-in with a non-empty unsaved
  // working deck, offer to save it to their account.
  useEffect(() => {
    const was = prevUser.current;
    prevUser.current = user?.id ?? null;
    if (user && was == null && currentId == null && entries.length > 0) {
      setMigratePrompt(true);
    }
  }, [user, currentId, entries.length]);

  async function migrateWorkingDeck() {
    await saveDeck("Imported deck", commanderId, entries);
    setMigratePrompt(false);
  }
```

(`currentId` is already read from `useDecksStore()` in this component; `entries`, `commanderId` are
already defined above.)

Add the `UserMenu` to the header — put it first in the right-hand button group, before `TemplateMenu`:

```tsx
        <div className="flex items-center gap-2">
          <UserMenu />
          <TemplateMenu />
          <HeaderButton testid="open-decks" title="Saved decks" onClick={() => setDecksOpen(true)}>
            🗂 Decks
          </HeaderButton>
```

Add the migrate banner just inside the top of the returned `<div className="flex h-screen flex-col">`,
above `<OraclePhrasePanel />`:

```tsx
      {migratePrompt && (
        <div className="flex items-center justify-between gap-3 border-b border-accent/40 bg-accent/10 px-5 py-2 text-xs text-accent">
          <span>Save the deck you’re building to your account?</span>
          <span className="flex gap-2">
            <button
              onClick={() => void migrateWorkingDeck()}
              className="rounded border border-accent/60 px-2 py-1 font-semibold hover:bg-accent/20"
            >
              Save it
            </button>
            <button
              onClick={() => setMigratePrompt(false)}
              className="rounded border border-edge px-2 py-1 text-zinc-400 hover:text-zinc-200"
            >
              Not now
            </button>
          </span>
        </div>
      )}
```

- [ ] **Step 2: Gate the Decks panel on auth**

In `frontend/src/components/DeckManagerPanel.tsx`, import the auth store and short-circuit the body when
logged out. Add at the top of the component (after the existing hooks):

```tsx
  const user = useAuth((s) => s.user);
```

with the import:

```tsx
import { useAuth } from "@/store/auth";
```

Then, right after the panel's header markup (where the saved-deck list would render), render a login
prompt instead when `!user`. Wrap the existing list/body in `{user ? ( …existing body… ) : (`:

```tsx
        {!user ? (
          <div className="px-4 py-10 text-center text-xs text-zinc-500">
            Log in to save decks to your account.
            <br />
            (Your current deck still autosaves in this browser.)
          </div>
        ) : (
          /* existing saved-deck list/body unchanged */
        )}
```

(Keep the existing body exactly as-is inside the `user ?` branch — only wrap it.)

- [ ] **Step 3: Type-check + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: no type errors; build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/page.tsx frontend/src/components/DeckManagerPanel.tsx
git commit -m "feat: hydrate auth, header user menu, migrate-on-login, gate saved decks"
```

---

## Task 10: Deploy — share the JWT secret + ship

**Files:**
- Modify: `deploy/systemd/deckdoctor-api.service`
- Modify: `deploy/DEPLOY.md`

- [ ] **Step 1: Document the secret env in the unit**

In `deploy/systemd/deckdoctor-api.service`, add under the existing `Environment=DATABASE_URL=...` line:

```
Environment=SIMMANDER_JWT_SECRET=CHANGE_ME_TO_TRACKER_SECRET
Environment=SIMMANDER_JWT_ALG=HS256
```

- [ ] **Step 2: Document the deploy step in DEPLOY.md**

In `deploy/DEPLOY.md` §4 (Services), add a note before the `systemctl enable` line:

```markdown
Deck Doctor validates the tracker's shared session, so it needs the SAME JWT secret the tracker signs
with. On the VPS, read it from the tracker config and put it in the api unit:
```bash
sudo grep -i 'secret_key' /opt/simmander-tracker/backend/config.ini   # copy the value
sudo sed -i 's|SIMMANDER_JWT_SECRET=.*|SIMMANDER_JWT_SECRET=<the tracker secret>|' \
  /etc/systemd/system/deckdoctor-api.service
```
```

- [ ] **Step 3: Commit + push**

```bash
git add deploy/systemd/deckdoctor-api.service deploy/DEPLOY.md
git commit -m "deploy: wire the shared JWT secret into the api unit"
git push origin main
```

- [ ] **Step 4: Deploy to the VPS**

```bash
ssh trashdad@simtrack 'bash -s' <<'EOF'
set -e
cd /opt/deck-doctor && sudo -u simmander git pull --quiet
sudo -u simmander ./.venv/bin/pip install -q -r backend/requirements.txt   # PyJWT
SECRET=$(sudo grep -iP '^\s*secret_key' /opt/simmander-tracker/backend/config.ini | head -1 | sed 's/.*=\s*//')
sudo sed -i "s|SIMMANDER_JWT_SECRET=.*|SIMMANDER_JWT_SECRET=$SECRET|" /etc/systemd/system/deckdoctor-api.service
cd /opt/deck-doctor/frontend && sudo -u simmander npm run build && sudo -u simmander cp -r .next/static .next/standalone/.next/static
sudo systemctl daemon-reload && sudo systemctl restart deckdoctor-api deckdoctor-web
sleep 4
curl -s localhost:8002/auth/me   # {"user":null} when no cookie
EOF
```

Expected: `{"user":null}` (anonymous loopback request — the validation path is live).

---

## Task 11: End-to-end verification (Playwright, against the live site)

> Login integration can only be exercised against a running tracker. Run this against the deployed
> `https://simmander.app/deck-doctor` after Task 10 (local dev has no tracker for `/api/auth/login`).

- [ ] **Step 1: Manual/Playwright flow**

Use real credentials for a test account. Verify:
1. `https://simmander.app/deck-doctor` shows **Log in** in the header (anonymous).
2. Build a deck (add a commander + a few cards) → header **Log in** → modal → submit valid credentials →
   modal closes, header shows the username, the **migrate banner** appears.
3. Click **Save it** → open 🗂 Decks → the deck is listed under the account.
4. Reload the page → still logged in (cookie), deck still listed.
5. **Log out** → header shows **Log in** again; 🗂 Decks shows "Log in to save decks…".
6. The tracker at `https://simmander.app/` reflects the same login/logout (shared session).

- [ ] **Step 2: Confirm the tracker is unaffected**

Run: `curl -s -o /dev/null -w "%{http_code}\n" https://simmander.app/` and `…/api/settings`
Expected: `200` for both.

- [ ] **Step 3: Final commit (docs/memory only if needed)**

No code change here; if you keep a run log, commit it. Otherwise the feature is complete.

---

## Self-review notes
- **Spec coverage:** auth validation (T3), user-scoped decks (T4–T6), in-app modal + shared login (T7–T9),
  migrate-on-login (T9), shared logout (T7/T9), nullable user_id (T4), deployment secret (T10), tests
  (T3/T6/T11) — all mapped.
- **Local-dev caveat:** `/api/auth/login` only resolves where the tracker runs (prod, or a local tracker).
  Backend auth unit tests don't need the tracker (they mint tokens with the shared secret). The login UI
  is prod-verified in T11.
- **Out of scope:** register/password-reset UI (links out), tier gating, reading username from the tracker DB.
