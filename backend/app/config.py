"""Runtime configuration.

Data sources are env-driven so the same backend serves the bundled sample data
in dev and the real simmander card DB + generated score store in production.
This is the documented seam for Phase 0 / Phase 3 (see docs/asset-inventory.md):
point SIMMANDER_CARDS / SIMMANDER_SCORES at the real assets and nothing else changes.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_REPO_ROOT = Path(__file__).resolve().parents[2]

CARDS_PATH = Path(os.environ.get("SIMMANDER_CARDS", _REPO_ROOT / "data" / "cards.json"))

# --- Postgres (the deckdoctor database) ------------------------------------
# The running app reads/writes Postgres only. The read-only analytical tables are
# loaded into it from the offline SQLite build artifacts by
# scoring/load_to_postgres.py; userdecks is read-write (app/decks.py). In prod set
# DATABASE_URL to the VPS's deckdoctor database (its own DB on the shared PG server).
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://deckdoctor:deckdoctor@localhost:5432/deckdoctor"
)

# --- Shared auth (validate the tracker's simmander_session JWT) -------------
# The SAME secret + algorithm the tracker signs its JWTs with (tracker
# backend/config.ini [auth]). In prod this is set from the tracker's secret via
# the systemd unit; the dev default only validates locally-minted test tokens.
SIMMANDER_JWT_SECRET = os.environ.get("SIMMANDER_JWT_SECRET", "dev-insecure-deckdoctor-secret")
SIMMANDER_JWT_ALG = os.environ.get("SIMMANDER_JWT_ALG", "HS256")

# --- Offline build artifacts (SQLite) --------------------------------------
# These are the pipeline's intermediate output, consumed by load_to_postgres.py.
# They are NOT read at request time; the app uses Postgres above.
SCORES_PATH = Path(os.environ.get("SIMMANDER_SCORES", _REPO_ROOT / "data" / "scores.sqlite"))
EDHREC_PATH = Path(os.environ.get("SIMMANDER_EDHREC", _REPO_ROOT / "data" / "edhrec.sqlite"))
SPELLBOOK_PATH = Path(os.environ.get("SIMMANDER_SPELLBOOK", _REPO_ROOT / "data" / "spellbook.sqlite"))
DECKS_PATH = Path(os.environ.get("SIMMANDER_DECKS", _REPO_ROOT / "data" / "decks.sqlite"))

# CORS origins for the React dev server / deployed frontend.
CORS_ORIGINS = os.environ.get(
    "SIMMANDER_CORS_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://localhost:5173",
).split(",")
