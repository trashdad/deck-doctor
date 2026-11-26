"""SIMMANDER_LAND_META: the card-update pipeline promotes land_meta.json into an untracked
dir and points the API at it; unset, the tracked backend/data/land_meta.json is used.
Pure tests: no database, no card file."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.store import (DEFAULT_LAND_META_PATH, LAND_META_ENV, Store,  # noqa: E402
                       land_meta_path)


def test_default_is_the_tracked_file(monkeypatch):
    monkeypatch.delenv(LAND_META_ENV, raising=False)
    assert land_meta_path() == DEFAULT_LAND_META_PATH
    assert DEFAULT_LAND_META_PATH.parts[-3:] == ("backend", "data", "land_meta.json")


def test_blank_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv(LAND_META_ENV, "  ")
    assert land_meta_path() == DEFAULT_LAND_META_PATH


def test_env_path_is_loaded(monkeypatch, tmp_path):
    meta = {"land1": {"name": "Test Land", "produced_mana": ["G"], "usd": 0.5}}
    p = tmp_path / "land_meta.json"
    p.write_text(json.dumps(meta), encoding="utf-8")
    monkeypatch.setenv(LAND_META_ENV, str(p))
    s = Store.__new__(Store)          # skip __init__ (no DB, no card file)
    s._load_land_meta(Path("unused"))
    assert s.land_meta == meta


def test_missing_env_file_gives_empty_meta(monkeypatch, tmp_path):
    monkeypatch.setenv(LAND_META_ENV, str(tmp_path / "absent.json"))
    s = Store.__new__(Store)
    s._load_land_meta(Path("unused"))
    assert s.land_meta == {}
