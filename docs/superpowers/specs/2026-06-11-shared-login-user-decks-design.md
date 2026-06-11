# Shared login + user-scoped decks — Design Spec (build-ready)

**Date:** 2026-06-11 · **Status:** approved (brainstorm), ready to plan
**Sub-feature A** of the Deck Doctor accounts/export/affiliate program (A → B → C → D).

## Goal
Let a logged-in simmander.app user use the SAME login on Deck Doctor (`simmander.app/deck-doctor`),
and have their saved decks belong to that account. No new login system — reuse the tracker's auth.

## How the tracker auth works (verified)
- Tracker issues a **JWT** (HS256, secret in the tracker's `backend/config.ini [auth].secret_key`,
  claims `{"sub": str(user_id), "admin": bool, "exp": ...}`).
- On login it sets cookie **`simmander_session`** = that JWT, on **domain `.simmander.app`, path `/`,
  HttpOnly, Secure, SameSite=Lax**.
- Users live in the `simmander_tracker` Postgres DB: `users(id SERIAL PK, username, email, tier, …)`.
- Login/register/logout endpoints are the tracker's `POST /api/auth/{login,register,logout}` (served at
  the simmander.app root by the tracker backend on :8000).

Because Deck Doctor is the **same origin** (`https://simmander.app`), the browser already sends
`simmander_session` to `/deck-doctor/api/*`. Deck Doctor just has to validate the JWT.

## Decisions (locked)
1. **Storage:** decks stay in Deck Doctor's own `deckdoctor` DB; add `user_id` (the tracker user id) —
   no cross-DB coupling.
2. **Logged-out UX:** full tool works anonymously with the existing localStorage autosave; login is
   purely additive and **migrates** the current working deck into the account on first login.
3. **Login UI:** in-app modal in Deck Doctor that POSTs to the shared `/api/auth/login` (same origin →
   sets the shared cookie). Register / password-reset link out to the tracker.
4. **Logout is shared** (clears the shared cookie → logged out of both apps).
5. `user_id` is **nullable** so pre-existing/anonymous-saved decks don't break.

## Backend (Deck Doctor — `backend/app/`)
- **`auth.py`** (new): reads the `simmander_session` cookie, decodes+verifies the JWT with the shared
  secret (HS256) via **PyJWT**, checks `exp` + signature.
  - `current_user(request) -> dict | None` → `{"id": int, "username": str|None, "is_admin": bool}` or
    None (anonymous). The username isn't in the JWT; v1 returns id + admin from claims and leaves
    username None (the frontend already knows it from the login response). No tracker-DB query.
  - `require_user(request) -> dict` → 401 if anonymous.
  - Secret + algorithm from `config.SIMMANDER_JWT_SECRET` / `SIMMANDER_JWT_ALG` (default HS256).
- **`config.py`**: add `SIMMANDER_JWT_SECRET`, `SIMMANDER_JWT_ALG`.
- **`decks.py`** (UserDecks): schema gains `user_id INTEGER` (nullable) + index. All reads/writes take a
  `user_id` filter:
  - `list_decks(user_id)`, `get(deck_id, user_id)`, `create(user_id, …)`, `update(deck_id, user_id, …)`,
    `delete(deck_id, user_id)` — every op scoped so user A can never touch user B's rows.
  - Anonymous (user_id None): the deck routes 401 (saving requires login); the frontend keeps using
    localStorage for the working deck when logged out.
- **`main.py`** deck routes (`/decks*`) depend on `require_user` and pass `user["id"]` through. New
  **`GET /deck-doctor/api/auth/me`** → `current_user(...)` (returns `{id, username, is_admin}` or 401/null
  for anonymous; used by the frontend to hydrate auth state). The route is reached as
  `/deck-doctor/api/auth/me` (Deck Doctor's own API), distinct from the tracker's `/api/auth/*`.
- **`requirements.txt`**: add `pyjwt`.

## Frontend (`frontend/src/`)
- **`store/auth.ts`** (zustand): `{user: {id, username} | null, ready, login(u,p), logout(), refresh()}`.
  - `refresh()` → GET `/deck-doctor/api/auth/me` (credentials included). The cookie/JWT is the source of
    truth for *whether* you're logged in (returns `{id, is_admin}`); the **username** is cached in
    `localStorage` (`simmander.user`) from the login response for display. So `refresh()` = "auth/me says
    a valid session for id X" + "use the cached display name for X" (clear the cache if auth/me is
    anonymous, or if the cached id ≠ the session id). This avoids any Deck Doctor → tracker-DB coupling
    just to show a name; a stale cached username is cosmetic only.
  - `login(u,p)` → POST `/api/auth/login` (the tracker, same origin, `credentials:'include'`) → on success
    the shared cookie is set; cache `{id, username}` in localStorage; store `user`; then trigger the
    deck-migration prompt.
  - `logout()` → POST `/api/auth/logout` (tracker) → clear `user` + the localStorage cache.
- **`components/LoginModal.tsx`**: username + password form posting via `login()`; error display; links
  out to simmander.app for register + password reset.
- **`app/page.tsx` header**: a `UserMenu` — "Log in" (opens modal) when anonymous; `username ▾` with
  "Log out" when authed. Hydrate via `useAuth().refresh()` on mount.
- **Deck persistence wiring** (`store/decks.ts` + `DeckManagerPanel`): when `user` is null, the Decks
  panel shows "Log in to save decks to your account" and the save actions are disabled (working deck
  still autosaves to localStorage). When `user` is set, the panel lists/saves account decks via the
  now-scoped `/decks` API.
- **`lib/api.ts`**: all deck calls already go to `/deck-doctor/api/*`; ensure `credentials:'include'` so
  the cookie rides along. Add `authMe()`, and `login()/logout()` hitting the tracker's `/api/auth/*`.

## Migration on login
On a successful login, if the current working deck (localStorage autosave) is non-empty and not already
an account deck, show a one-shot prompt: **"Save this deck to your account?"** → POST `/decks` (now
user-scoped). Decline = leave it local. Keeps the anonymous→logged-in transition lossless.

## Deployment
- The Deck Doctor backend needs the tracker's JWT secret. On the VPS, read it from the tracker's
  `config.ini` and set `SIMMANDER_JWT_SECRET` in `deckdoctor-api.service` (env). I have sudo there.
- Add a migration step for the `user_id` column (UserDecks already does `CREATE TABLE IF NOT EXISTS`;
  add an idempotent `ALTER TABLE … ADD COLUMN IF NOT EXISTS user_id INTEGER` + index on startup).

## Testing
- **Backend** (`tests/test_auth.py`, `tests/test_decks.py`): JWT validation (valid / expired / wrong-secret
  / missing cookie → right user or None/401); deck endpoints scoped (user A's token can't list/get/update/
  delete user B's decks); `auth/me` shapes. Sign test JWTs with a known test secret via env override.
- **Playwright** (live or local): open modal → log in → save a deck → reload → deck persists under the
  account → log out → deck not listed anonymously; logging in with a non-empty working deck shows the
  migrate prompt.

## Out of scope (v1)
Register/password-reset UI inside Deck Doctor (link out); tier-gating any Deck Doctor feature; reading
username/email from the tracker DB (use the login response + JWT claims). Sharing decks publicly.
