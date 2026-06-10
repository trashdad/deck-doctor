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
SCORES_PATH = Path(os.environ.get("SIMMANDER_SCORES", _REPO_ROOT / "data" / "scores.sqlite"))
EDHREC_PATH = Path(os.environ.get("SIMMANDER_EDHREC", _REPO_ROOT / "data" / "edhrec.sqlite"))
# SP6: user deck persistence (read-write, owned by app/decks.py, NOT by Store)
USERDECKS_PATH = Path(os.environ.get("SIMMANDER_USERDECKS", _REPO_ROOT / "data" / "userdecks.sqlite"))
# SP7: Commander Spellbook combo DB (read-only, built by tools/import_spellbook/)
SPELLBOOK_PATH = Path(os.environ.get("SIMMANDER_SPELLBOOK", _REPO_ROOT / "data" / "spellbook.sqlite"))
# Scraped decklist corpus (read-only) — drives commander popularity (deck count per commander).
DECKS_PATH = Path(os.environ.get("SIMMANDER_DECKS", _REPO_ROOT / "data" / "decks.sqlite"))

# CORS origins for the React dev server / deployed frontend.
CORS_ORIGINS = os.environ.get(
    "SIMMANDER_CORS_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://localhost:5173",
).split(",")
