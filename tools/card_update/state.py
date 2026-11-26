"""Persistent pipeline state (one JSON file, written atomically).

A corrupt state file is an error, never silently reset: resetting would forget which
release is live and which upstream versions were already promoted.
"""

from __future__ import annotations

import json
import typing
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from card_update.fsutil import atomic_write_json


class StateError(Exception):
    """State file unreadable or malformed."""


@dataclass
class State:
    # upstream versions behind the live release
    scryfall_updated_at: str | None = None
    mtgish_sha: str | None = None
    # live release
    cards_sha256: str | None = None
    land_meta_sha256: str | None = None
    current_release_id: str | None = None
    last_promoted_utc: str | None = None
    # health of the job
    consecutive_failures: int = 0
    last_success_utc: str | None = None
    last_failure_utc: str | None = None
    last_failure_stage: str | None = None
    last_failure_message: str | None = None
    last_run_id: str | None = None
    last_run_result: str | None = None
    # MTGish operators the live tag taxonomy does not map (baseline for "new operators")
    last_unmapped_operators: int | None = None
    unmapped_operators_sha256: str | None = None
    # sha256 of the scoring code that computed the live store's IER (see fingerprint.py);
    # "unknown" = live store built by unrecorded code (init --baseline-from-store)
    scoring_fingerprint: str | None = None
    # Durable transaction marker, written BEFORE any live file changes and cleared only
    # after rebuild + health pass (see txn.py). Anyone finding it set (next run,
    # `recover`, the API's ExecStartPre) restores release `restore_to` first:
    # {"kind": "promote"|"rollback", "run_id", "restore_to", "needs_rebuild", "phase",
    #  "started_utc"}
    transaction: dict[str, Any] | None = None
    version: int = 2


def _coerce(name: str, value: Any, tp: Any) -> Any:
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if value is None and type(None) in args:
        return None
    base = next((a for a in args if a is not type(None)), tp) if args and origin is not dict else tp
    base_origin = typing.get_origin(base) or base
    expected = {int: int, str: str, dict: dict}.get(base_origin)
    if expected is None:
        return value
    if expected is int and isinstance(value, bool):
        raise StateError(f"state field '{name}' must be int, got {value!r}")
    if not isinstance(value, expected):
        raise StateError(f"state field '{name}' must be {expected.__name__}, got {value!r}")
    return value


def load_state(path: Path) -> State:
    path = Path(path)
    if not path.exists():
        return State()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StateError(f"cannot read state file {path}: {exc} — fix or restore it by hand; "
                         "it records which release is live") from None
    if not isinstance(raw, dict):
        raise StateError(f"state file {path} must hold a JSON object")
    hints = typing.get_type_hints(State)
    known = {f.name for f in fields(State)}
    kwargs = {k: _coerce(k, v, hints[k]) for k, v in raw.items() if k in known}
    return State(**kwargs)


def save_state(path: Path, state: State) -> None:
    atomic_write_json(Path(path), asdict(state))


def state_dict(state: State) -> dict[str, Any]:
    return asdict(state)
