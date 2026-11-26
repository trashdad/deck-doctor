"""Access to logic that already lives in the repo, so the pipeline reuses it instead of
copying it: prep_cards' print filter, enrich_lands' field extraction and constants, and
the fingerprint QA unmapped-operator report (run in a child process so the scoring
package's sys.path setup never leaks into this process).
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Protocol

from card_update.procs import CommandRunner

_REPORT_SCRIPT = Path(__file__).resolve().parent / "unmapped_report.py"


class RepoBridge(Protocol):
    def keep_card(self) -> Callable[[dict], bool]: ...

    def enrich_module(self) -> Any: ...

    def unmapped_operators(self, mtgish_path: Path) -> list[tuple[str, int]]: ...


def load_module_from(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FileRepoBridge:
    def __init__(self, app_dir: Path, python: str, runner: CommandRunner, timeout_s: float = 1800) -> None:
        self.app_dir = Path(app_dir)
        self.python = python
        self.runner = runner
        self.timeout_s = timeout_s

    def keep_card(self) -> Callable[[dict], bool]:
        mod = load_module_from(self.app_dir / "scoring" / "prep_cards.py", "_card_update_prep_cards")
        return mod._keep  # noqa: SLF001 - the exact filter prep_cards applies

    def enrich_module(self) -> Any:
        return load_module_from(self.app_dir / "backend" / "scripts" / "enrich_lands.py",
                                "_card_update_enrich_lands")

    def unmapped_operators(self, mtgish_path: Path) -> list[tuple[str, int]]:
        with tempfile.TemporaryDirectory(prefix="card_update_unmapped_") as tmp:
            out = Path(tmp) / "unmapped.json"
            res = self.runner.run(
                [self.python, str(_REPORT_SCRIPT), "--scoring-dir", str(self.app_dir / "scoring"),
                 "--mtgish", str(mtgish_path), "--out", str(out)],
                cwd=self.app_dir, timeout_s=self.timeout_s, label="unmapped_report")
            if res.returncode != 0:
                raise RuntimeError(f"unmapped_report exited {res.returncode}: {res.tail_text()}")
            return [(op, int(n)) for op, n in json.loads(out.read_text(encoding="utf-8"))]
