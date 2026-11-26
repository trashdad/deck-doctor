"""Offline end-to-end harness: real scoring scripts on the tiny fixtures, fake network,
fake rebuild script and fake API. Live paths all live under a tmp dir."""

from __future__ import annotations

import gzip
import io
import json
import logging
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from card_update.config import load_config
from card_update.context import Services
from card_update.fsutil import sha256_file
from card_update.http import DownloadResult, FetchError
from card_update.procs import CommandResult, SubprocessRunner
from card_update.repo_bridge import FileRepoBridge
from card_update.snapshot import finalize_sqlite

FIX = Path(__file__).resolve().parent / "fixtures"
REPO = Path(__file__).resolve().parents[3]
BULK_URL = "https://api.scryfall.com/bulk-data/default-cards"
HEAD_URL = "https://api.github.com/repos/i5jb/mtgish/commits/HEAD"
GZ_URL = "https://data.scryfall.io/default-cards/default-cards-20261126.jsonl.gz"
NEW_SHA = "b" * 40
OLD_SHA = "a" * 40
UPDATED_AT = "2026-11-26T10:06:21.722+00:00"
SOL_RING_REPRINT = "00000000-0000-4000-8000-00000000501a"


def scryfall_prints() -> list[dict]:
    return [json.loads(x) for x in (FIX / "scryfall_sample.jsonl").read_text(encoding="utf-8").splitlines() if x]


def _run(argv: list[str]) -> None:
    import subprocess
    subprocess.run(argv, cwd=REPO, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def build_baseline(dest: Path) -> None:
    """The 'live' release before the update: no Lightning Bolt, no reprint/token/foreign prints."""
    dest.mkdir(parents=True, exist_ok=True)
    base = [p for p in scryfall_prints() if p["name"] != "Lightning Bolt"
            and p["id"] != SOL_RING_REPRINT and p.get("layout") != "token" and p.get("lang") == "en"]
    src = dest / "src.json"
    src.write_text(json.dumps(base), encoding="utf-8")
    py, sc = sys.executable, REPO / "scoring"
    mt = str(FIX / "mtgish_sample.lines.json")
    _run([py, str(sc / "prep_cards.py"), "--src", str(src), "--out", str(dest / "cards.json")])
    db = str(dest / "scores.sqlite")
    _run([py, str(sc / "build_store.py"), "--cards", str(dest / "cards.json"), "--out", db])
    _run([py, str(sc / "build_semantics.py"), "--mtgish", mt, "--cards", str(dest / "cards.json"), "--db", db])
    _run([py, str(sc / "build_fingerprints.py"), "--mtgish", mt, "--cards", str(dest / "cards.json"),
          "--db", db, "--outliers", str(dest / "no-outliers")])
    finalize_sqlite(dest / "scores.sqlite")
    cards = json.loads((dest / "cards.json").read_text(encoding="utf-8"))
    meta = {c["id"]: {"name": c["name"], "produced_mana": ["C"], "usd": 1.0}
            for c in cards if "Land" in c["type_line"]}
    (dest / "land_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    src.unlink()


def gz_bytes() -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write((FIX / "scryfall_sample.jsonl").read_bytes())
    return buf.getvalue()


class FakeFetcher:
    def __init__(self, gz: bytes, *, mtgish_sha: str = NEW_SHA, updated_at: str = UPDATED_AT,
                 fail: set[str] | None = None, license_text: str = "MIT License\n\nCopyright (c) mtgish team\n"):
        self.gz = gz
        self.mtgish_sha = mtgish_sha
        self.updated_at = updated_at
        self.fail = fail or set()
        self.license_text = license_text
        self.calls: list[tuple[str, str]] = []

    def _maybe_fail(self, url: str) -> None:
        if any(f in url for f in self.fail):
            raise FetchError(f"simulated failure for {url}")

    def get_json(self, url: str, *, accept: str = "application/json") -> Any:
        self.calls.append(("GET", url))
        self._maybe_fail(url)
        if url == BULK_URL:
            return {"object": "bulk_data", "type": "default_cards", "updated_at": self.updated_at,
                    "jsonl_download_uri": GZ_URL, "compressed_size": len(self.gz)}
        if url == HEAD_URL:
            return {"sha": self.mtgish_sha}
        raise FetchError(f"unexpected GET {url}")

    def post_json(self, url: str, payload: Any) -> Any:
        self.calls.append(("POST", url))
        self._maybe_fail(url)
        return {"data": [{"id": i["id"], "name": "Land " + i["id"][:4], "produced_mana": ["G", "U"],
                          "prices": {"usd": "0.25"}} for i in payload["identifiers"]], "not_found": []}

    def get_text(self, url: str, *, max_bytes: int = 1_000_000) -> str:
        self.calls.append(("GET", url))
        self._maybe_fail(url)
        return self.license_text

    def download(self, url: str, dest: Path, *, expected_size=None, expected_sha256=None, min_size=0,
                 max_size=None) -> DownloadResult:
        self.calls.append(("DOWNLOAD", url))
        self._maybe_fail(url)
        data = self.gz if url == GZ_URL else (FIX / "mtgish_sample.lines.json").read_bytes()
        if expected_size is not None and len(data) != expected_size:
            raise FetchError(f"size {len(data)} != expected {expected_size}")
        if len(data) < min_size:
            raise FetchError(f"below min {min_size}")
        Path(dest).write_bytes(data)
        return DownloadResult(url=url, path=Path(dest), size=len(data), sha256=sha256_file(Path(dest)))


@dataclass
class FakeApi:
    """The Deck Doctor API after a reload: reports the live cards.json count.
    ``broken_counts`` simulates a release that makes the API unhealthy."""
    live_cards: Path
    broken_counts: set[int] = field(default_factory=set)
    calls: int = 0
    engines: int = 50
    edhrec_commanders: int = 20
    spellbook_combos: int = 30
    down: bool = False

    def get_json(self, url: str, *, accept: str = "application/json") -> Any:
        self.calls += 1
        if self.down:
            raise FetchError("connection refused (fake API down)")
        n = len(json.loads(self.live_cards.read_text(encoding="utf-8")))
        if n in self.broken_counts:
            return {"status": "error", "cards": n}
        return {"status": "ok", "scores_loaded": True, "cards": n, "engines": self.engines,
                "edhrec_commanders": self.edhrec_commanders, "spellbook_combos": self.spellbook_combos}


def write_rebuilt_tables(scores: Path, rows: int) -> None:
    """What build_relationships + build_cooccurrence leave in the live store."""
    import sqlite3
    con = sqlite3.connect(scores)
    try:
        for t in ("card_relationships", "engines", "card_cooccurrence"):
            con.execute(f"CREATE TABLE IF NOT EXISTS {t} (a TEXT, b TEXT)")
            con.execute(f"DELETE FROM {t}")
            con.executemany(f"INSERT INTO {t} VALUES (?, ?)", [(str(i), str(i + 1)) for i in range(rows)])
        con.commit()
    finally:
        con.close()


class FakeRunner:
    """Real subprocesses for the scoring scripts; the bash rebuild script is faked: it
    rebuilds the relationship/co-occurrence tables in the live store (``rebuild_rows``
    rows each) and exits with the next code from ``rebuild_rcs`` (shared across runs)."""

    def __init__(self, log: logging.Logger, hh: "Harness"):
        self.real = SubprocessRunner(log)
        self.hh = hh
        self.rebuild_calls: list[dict] = []

    def run(self, argv, *, cwd, timeout_s, label, env=None) -> CommandResult:
        if argv and argv[0] == "bash":
            self.rebuild_calls.append(dict(env or {}))
            rc = self.hh.rebuild_rcs.pop(0) if self.hh.rebuild_rcs else 0
            if rc == 0:
                rows = self.hh.rebuild_rows
                if isinstance(rows, list):          # per-call row counts
                    rows = rows.pop(0) if len(rows) > 1 else rows[0]
                write_rebuilt_tables(self.hh.live_scores, rows)
                for k, v in self.hh.api_after_rebuild.items():
                    setattr(self.hh.api, k, v)
                self.hh.api_after_rebuild = {}
            return CommandResult(tuple(argv), rc, 0.1, ("fake rebuild",))
        return self.real.run(argv, cwd=cwd, timeout_s=timeout_s, label=label, env=env)


@dataclass
class Harness:
    root: Path
    baseline: Path
    gz: bytes
    clock: Any
    fetcher: FakeFetcher = None  # type: ignore[assignment]
    api: FakeApi = None  # type: ignore[assignment]
    rebuild_rcs: list[int] = field(default_factory=list)
    rebuild_rows: Any = 10                 # int, or a list consumed per rebuild
    api_after_rebuild: dict = field(default_factory=dict)     # applied once, by the next good rebuild
    runners: list[FakeRunner] = field(default_factory=list)
    overrides: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        cur = self.root / "card-data" / "current"
        cur.mkdir(parents=True)
        (self.root / "data").mkdir()
        shutil.copy(self.baseline / "cards.json", cur / "cards.json")
        shutil.copy(self.baseline / "land_meta.json", cur / "land_meta.json")
        shutil.copy(self.baseline / "scores.sqlite", self.root / "data" / "scores.sqlite")
        write_rebuilt_tables(self.live_scores, 10)        # live store as the nightly refresh leaves it
        self.fetcher = self.fetcher or FakeFetcher(self.gz)
        self.api = self.api or FakeApi(cur / "cards.json")

    @property
    def live_cards(self) -> Path:
        return self.root / "card-data" / "current" / "cards.json"

    @property
    def live_scores(self) -> Path:
        return self.root / "data" / "scores.sqlite"

    @property
    def state_file(self) -> Path:
        return self.root / "card-data" / "state.json"

    def config_dict(self) -> dict:
        cfg = {
            "paths": {"app_dir": str(REPO), "card_data_dir": str(self.root / "card-data"),
                      "live_scores": str(self.live_scores), "lock_file": str(self.root / "data" / ".pipeline.lock"),
                      "outliers_dir": str(self.root / "no-outliers"), "python": sys.executable},
            "fetch": {"scryfall_min_bytes": 100, "mtgish_min_bytes": 100, "min_free_bytes": 1},
            "prep": {"min_scryfall_prints": 5},
            "lock": {"wait_minutes": 0},
            "gates": {"min_cards": 5},
            "health": {"timeout_s": 30, "poll_interval_s": 5},
        }
        for section, values in self.overrides.items():
            cfg.setdefault(section, {}).update(values)
        return cfg

    def config_path(self) -> Path:
        p = self.root / "cfg.json"
        p.write_text(json.dumps(self.config_dict()), encoding="utf-8")
        return p

    def config(self):
        return load_config(self.config_path(), environ={})

    def services_builder(self):
        def builder(cfg, clock):
            def build(log):
                runner = FakeRunner(log, self)
                self.runners.append(runner)
                bridge = FileRepoBridge(cfg.paths.app_dir, cfg.paths.python, runner)
                return Services(fetcher=self.fetcher, api=self.api, runner=runner, clock=clock, bridge=bridge)
            return build
        return builder

    def rebuild_calls(self) -> list[dict]:
        return [c for r in self.runners for c in r.rebuild_calls]

    def main(self, *argv: str) -> tuple[int, str]:
        from card_update.cli import main
        out = io.StringIO()
        code = main(["--config", str(self.config_path()), *argv], environ={}, clock=self.clock,
                     services=self.services_builder(), stream=out)
        return code, out.getvalue()

    def state(self) -> dict:
        return json.loads(self.state_file.read_text(encoding="utf-8")) if self.state_file.exists() else {}

    def live_names(self) -> set[str]:
        return {c["name"] for c in json.loads(self.live_cards.read_text(encoding="utf-8"))}

    def run_dirs(self) -> list[Path]:
        d = self.root / "card-data" / "runs"
        return sorted(d.iterdir()) if d.exists() else []
