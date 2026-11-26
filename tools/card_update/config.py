"""Typed configuration: built-in defaults <- JSON file <- environment overrides.

Environment overrides use ``CARD_UPDATE__<SECTION>__<KEY>=<value>``; the value is parsed
as JSON when it parses (numbers, true/false, lists), else taken as a string. Unknown
sections/keys and out-of-range values are rejected (fail closed; exit code 2).
Python 3.10 compatible: no tomllib.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import types
import typing
from dataclasses import dataclass, field, fields
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

ENV_PREFIX = "CARD_UPDATE__"
DEFAULT_USER_AGENT = "DeckDoctor-CardUpdate/1.0 (+https://simmander.app/deck-doctor)"

DEFAULT_STAGE_ORDER = (
    "check", "fetch", "prep", "enrich", "build", "verify",
    "approve", "promote", "rebuild", "health", "cleanup",
)
# Stages that may not be removed or reordered: together they are the fail-closed path.
ESSENTIAL_STAGES = ("check", "fetch", "prep", "build", "verify", "promote")
# Required after promote unless stages.allow_partial_promote (runs then end "partial").
LIVE_CHECK_STAGES = ("rebuild", "health")
OPTIONAL_STAGES = ("enrich", "approve", "cleanup")
DEFAULT_ALLOWED_HOSTS = ("scryfall.com", "scryfall.io", "api.github.com", "raw.githubusercontent.com",
                         "github.com", "objects.githubusercontent.com")

DEFAULT_SENTINELS = (
    "Sol Ring", "Arcane Signet", "Command Tower", "Birds of Paradise",
    "Cultivate", "Swords to Plowshares", "Rhystic Study",
)
DEFAULT_REQUIRED_FIELDS = ("id", "name", "oracle_id", "type_line", "color_identity", "cmc")
DEFAULT_REQUIRED_TABLES = (
    "cards", "synergies", "card_flat_tags", "card_ability_tags",
    "card_fingerprints", "card_fingerprint_flat", "tag_inverted_index",
)


class ConfigError(Exception):
    """Invalid configuration or usage (CLI exit code 2)."""


# ── sections ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PathsSection:
    app_dir: str = "/opt/deck-doctor"
    card_data_dir: str | None = None      # default <app_dir>/card-data
    live_cards: str | None = None         # default $SIMMANDER_CARDS or <card_data_dir>/current/cards.json
    live_land_meta: str | None = None     # default $SIMMANDER_LAND_META or <card_data_dir>/current/land_meta.json
    live_scores: str | None = None        # default <app_dir>/data/scores.sqlite (load_to_postgres reads it there)
    seed_cards: str | None = None         # default <app_dir>/data/cards.json (tracked; `init` only)
    seed_land_meta: str | None = None     # default <app_dir>/backend/data/land_meta.json (tracked; `init` only)
    lock_file: str | None = None          # default <app_dir>/data/.pipeline.lock (shared with refresh_corpus.sh)
    outliers_dir: str | None = None       # default <app_dir>/data/outliers (build_fingerprints)
    python: str | None = None             # default: the interpreter running this package


@dataclass(frozen=True)
class UpstreamSection:
    user_agent: str = DEFAULT_USER_AGENT
    scryfall_bulk_url: str = "https://api.scryfall.com/bulk-data/default-cards"
    scryfall_collection_url: str = "https://api.scryfall.com/cards/collection"
    mtgish_head_url: str = "https://api.github.com/repos/i5jb/mtgish/commits/HEAD"
    mtgish_data_url: str = "https://raw.githubusercontent.com/i5jb/mtgish/{sha}/data/mtgish.lines.json"
    mtgish_license_url: str = "https://raw.githubusercontent.com/i5jb/mtgish/{sha}/LICENSE"
    mtgish_license_must_contain: str = "MIT License"
    mtgish_pin_sha: str | None = None     # set to freeze MTGish at a commit instead of following HEAD


@dataclass(frozen=True)
class HttpSection:
    timeout_s: float = 60.0
    retries: int = 4
    backoff_s: float = 5.0
    backoff_max_s: float = 120.0
    min_interval_s: float = 0.1           # per host; Scryfall asks for <= 10 requests/second
    max_json_bytes: int = 20_000_000      # cap on any JSON response body
    # https only; a host matches an entry or any subdomain of it (redirects included)
    allowed_hosts: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWED_HOSTS))


@dataclass(frozen=True)
class LockSection:
    wait_minutes: float = 60.0


@dataclass(frozen=True)
class FetchSection:
    scryfall_min_bytes: int = 20_000_000
    scryfall_max_bytes: int = 2_000_000_000
    mtgish_min_bytes: int = 5_000_000
    mtgish_max_bytes: int = 1_000_000_000
    min_free_bytes: int = 3_000_000_000


@dataclass(frozen=True)
class PrepSection:
    min_scryfall_prints: int = 50_000
    max_scryfall_prints: int = 1_000_000
    max_decompressed_bytes: int = 6_000_000_000   # bulk JSONL after gunzip (2026-11: ~0.6 GB)
    timeout_minutes: float = 60.0


@dataclass(frozen=True)
class EnrichSection:
    batch_size: int = 75
    interval_s: float = 0.15
    max_error_batches: int = 0


@dataclass(frozen=True)
class BuildSection:
    top_k: int = 16
    step_timeout_minutes: float = 240.0


@dataclass(frozen=True)
class GatesSection:
    required_fields: list[str] = field(default_factory=lambda: list(DEFAULT_REQUIRED_FIELDS))
    min_count_ratio: float = 0.99
    max_count_ratio: float = 1.25
    min_cards: int = 25_000
    sentinels: list[str] = field(default_factory=lambda: list(DEFAULT_SENTINELS))
    max_tag_share_drop_pp: float = 2.0
    max_lost_all_tags_ratio: float = 0.01
    # MTGish operators without a tag mapping: NEW ones vs the live release's recorded set,
    # plus an absolute ceiling (2026-11: 1,469 distinct). First run records the baseline.
    max_new_unmapped_operators: int = 40
    max_unmapped_operators: int = 3000
    # Enforced only while the scoring code that built the live store is unchanged
    # (fingerprint.py); after a scoring-code change drift is logged as a WARNING.
    max_ier_changed_unchanged: int = 0
    required_tables: list[str] = field(default_factory=lambda: list(DEFAULT_REQUIRED_TABLES))
    min_land_meta_coverage: float = 0.99


@dataclass(frozen=True)
class ApproveSection:
    enabled: bool = False
    approvals_dir: str | None = None      # default <card_data_dir>/approvals
    wait_minutes: float = 0.0


@dataclass(frozen=True)
class RebuildSection:
    script: str = "deploy/rebuild_and_reload.sh"
    bash: str = "bash"
    timeout_minutes: float = 240.0


@dataclass(frozen=True)
class HealthSection:
    api_base: str = "http://127.0.0.1:8002"
    timeout_s: float = 300.0
    poll_interval_s: float = 5.0
    # After rebuild: card_relationships / engines / card_cooccurrence rows and the API's
    # engines / edhrec_commanders / spellbook_combos may not shrink by more than this
    # fraction vs the pre-promote reading (when known), and relationships/engines > 0.
    max_shrink_ratio: float = 0.25


@dataclass(frozen=True)
class RetentionSection:
    keep_releases: int = 3
    keep_runs: int = 5
    keep_log_days: int = 30


@dataclass(frozen=True)
class StatusSection:
    stale_after_days: float = 3.0


@dataclass(frozen=True)
class StagesSection:
    order: list[str] = field(default_factory=lambda: list(DEFAULT_STAGE_ORDER))
    # Dev/rehearsal only: allow promote without rebuild + health; such runs end "partial"
    # (no success mark, upstream stamps not advanced) with a loud warning.
    allow_partial_promote: bool = False


@dataclass(frozen=True)
class RunSection:
    deadline_hours: float = 12.0          # whole run; child timeouts are capped to what is left


@dataclass(frozen=True)
class Paths:
    """Resolved absolute paths."""
    app_dir: Path
    card_data_dir: Path
    live_cards: Path
    live_land_meta: Path
    live_scores: Path
    seed_cards: Path
    seed_land_meta: Path
    lock_file: Path
    outliers_dir: Path
    python: str
    current_dir: Path
    releases_dir: Path
    runs_dir: Path
    logs_dir: Path
    state_file: Path
    approvals_dir: Path


@dataclass(frozen=True)
class Config:
    paths: Paths
    upstream: UpstreamSection
    http: HttpSection
    lock: LockSection
    fetch: FetchSection
    prep: PrepSection
    enrich: EnrichSection
    build: BuildSection
    gates: GatesSection
    approve: ApproveSection
    rebuild: RebuildSection
    health: HealthSection
    retention: RetentionSection
    status: StatusSection
    stages: StagesSection
    run: RunSection
    source: str = "<defaults>"


_SECTIONS: Mapping[str, type] = MappingProxyType({
    "paths": PathsSection, "upstream": UpstreamSection, "http": HttpSection,
    "lock": LockSection, "fetch": FetchSection, "prep": PrepSection,
    "enrich": EnrichSection, "build": BuildSection, "gates": GatesSection,
    "approve": ApproveSection, "rebuild": RebuildSection, "health": HealthSection,
    "retention": RetentionSection, "status": StatusSection, "stages": StagesSection,
    "run": RunSection,
})


# ── parsing ──────────────────────────────────────────────────────────────────

def _check_type(where: str, value: Any, tp: Any) -> Any:
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if origin in (typing.Union, types.UnionType):     # only Optional[X] is used
        if value is None and type(None) in args:
            return None
        inner = [a for a in args if a is not type(None)]
        return _check_type(where, value, inner[0])
    if origin is list:
        if not isinstance(value, list):
            raise ConfigError(f"{where}: expected a list, got {type(value).__name__}")
        return [_check_type(f"{where}[{i}]", v, args[0]) for i, v in enumerate(value)]
    if tp is bool:
        if not isinstance(value, bool):
            raise ConfigError(f"{where}: expected true/false, got {value!r}")
        return value
    if tp is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{where}: expected an integer, got {value!r}")
        return value
    if tp is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"{where}: expected a number, got {value!r}")
        return float(value)
    if tp is str:
        if not isinstance(value, str):
            raise ConfigError(f"{where}: expected a string, got {value!r}")
        return value
    raise ConfigError(f"{where}: unsupported type {tp!r}")  # pragma: no cover


def _build_section(name: str, cls: type, raw: Mapping[str, Any]) -> Any:
    hints = typing.get_type_hints(cls)
    known = {f.name for f in fields(cls)}
    for key in raw:
        if key not in known:
            raise ConfigError(f"unknown key '{name}.{key}' (known: {', '.join(sorted(known))})")
    kwargs = {k: _check_type(f"{name}.{k}", v, hints[k]) for k, v in raw.items()}
    return cls(**kwargs)


def _env_overrides(environ: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key, raw in environ.items():
        if not key.startswith(ENV_PREFIX):
            continue
        parts = key[len(ENV_PREFIX):].lower().split("__")
        if len(parts) != 2 or not all(parts):
            raise ConfigError(f"bad override variable {key}: use {ENV_PREFIX}<SECTION>__<KEY>")
        try:
            value: Any = json.loads(raw)
        except ValueError:
            value = raw
        out.setdefault(parts[0], {})[parts[1]] = value
    return out


def _merge(base: dict[str, dict[str, Any]], over: Mapping[str, Any], origin: str) -> None:
    if not isinstance(over, Mapping):
        raise ConfigError(f"{origin}: top level must be a JSON object")
    for section, values in over.items():
        if section.startswith("_"):      # "_comment" keys are allowed for documentation
            continue
        if section not in _SECTIONS:
            raise ConfigError(f"{origin}: unknown section '{section}' "
                              f"(known: {', '.join(sorted(_SECTIONS))})")
        if not isinstance(values, Mapping):
            raise ConfigError(f"{origin}: section '{section}' must be an object")
        base.setdefault(section, {}).update(
            {k: v for k, v in values.items() if not k.startswith("_")})


def _resolve_paths(p: PathsSection, approve: ApproveSection, environ: Mapping[str, str]) -> Paths:
    app = Path(p.app_dir)
    card_data = Path(p.card_data_dir) if p.card_data_dir else app / "card-data"
    current = card_data / "current"

    def pick(explicit: str | None, env_name: str | None, default: Path) -> Path:
        if explicit:
            return Path(explicit)
        if env_name and environ.get(env_name):
            return Path(environ[env_name])
        return default

    return Paths(
        app_dir=app,
        card_data_dir=card_data,
        live_cards=pick(p.live_cards, "SIMMANDER_CARDS", current / "cards.json"),
        live_land_meta=pick(p.live_land_meta, "SIMMANDER_LAND_META", current / "land_meta.json"),
        live_scores=pick(p.live_scores, None, app / "data" / "scores.sqlite"),
        seed_cards=pick(p.seed_cards, None, app / "data" / "cards.json"),
        seed_land_meta=pick(p.seed_land_meta, None, app / "backend" / "data" / "land_meta.json"),
        lock_file=pick(p.lock_file, None, app / "data" / ".pipeline.lock"),
        outliers_dir=pick(p.outliers_dir, None, app / "data" / "outliers"),
        python=p.python or sys.executable,
        current_dir=current,
        releases_dir=card_data / "releases",
        runs_dir=card_data / "runs",
        logs_dir=card_data / "logs",
        state_file=card_data / "state.json",
        approvals_dir=Path(approve.approvals_dir) if approve.approvals_dir else card_data / "approvals",
    )


def _validate(cfg: Config) -> None:
    errors: list[str] = []

    def need(cond: bool, msg: str) -> None:
        if not cond:
            errors.append(msg)

    g = cfg.gates
    need(0 < g.min_count_ratio <= 1, "gates.min_count_ratio must be in (0, 1]")
    need(g.max_count_ratio >= 1, "gates.max_count_ratio must be >= 1")
    need(g.min_cards >= 1, "gates.min_cards must be >= 1")
    need(0 <= g.max_tag_share_drop_pp <= 100, "gates.max_tag_share_drop_pp must be in [0, 100]")
    need(0 <= g.max_lost_all_tags_ratio <= 1, "gates.max_lost_all_tags_ratio must be in [0, 1]")
    need(g.max_unmapped_operators >= 0, "gates.max_unmapped_operators must be >= 0")
    need(g.max_ier_changed_unchanged >= 0, "gates.max_ier_changed_unchanged must be >= 0")
    need(0 <= g.min_land_meta_coverage <= 1, "gates.min_land_meta_coverage must be in [0, 1]")
    need(bool(g.required_fields), "gates.required_fields must not be empty")
    need(bool(g.required_tables), "gates.required_tables must not be empty")
    need(1 <= cfg.enrich.batch_size <= 75, "enrich.batch_size must be 1..75 (Scryfall collection limit)")
    need(cfg.enrich.interval_s >= 0.1, "enrich.interval_s must be >= 0.1 (Scryfall: <= 10 req/s)")
    need(cfg.enrich.max_error_batches >= 0, "enrich.max_error_batches must be >= 0")
    need(cfg.http.retries >= 0, "http.retries must be >= 0")
    need(cfg.http.timeout_s > 0, "http.timeout_s must be > 0")
    need(cfg.http.backoff_s >= 0 and cfg.http.backoff_max_s >= cfg.http.backoff_s,
         "http.backoff_s must be >= 0 and <= http.backoff_max_s")
    need(cfg.http.min_interval_s >= 0.1, "http.min_interval_s must be >= 0.1 (Scryfall: <= 10 req/s)")
    need(cfg.lock.wait_minutes >= 0, "lock.wait_minutes must be >= 0")
    need(cfg.retention.keep_releases >= 1, "retention.keep_releases must be >= 1")
    need(cfg.retention.keep_runs >= 1, "retention.keep_runs must be >= 1")
    need(cfg.retention.keep_log_days >= 1, "retention.keep_log_days must be >= 1")
    need(cfg.status.stale_after_days > 0, "status.stale_after_days must be > 0")
    need(cfg.run.deadline_hours > 0, "run.deadline_hours must be > 0")
    need(0 <= cfg.health.max_shrink_ratio < 1, "health.max_shrink_ratio must be in [0, 1)")
    need(g.max_new_unmapped_operators >= 0, "gates.max_new_unmapped_operators must be >= 0")
    need(cfg.http.max_json_bytes > 0, "http.max_json_bytes must be > 0")
    need(bool(cfg.http.allowed_hosts), "http.allowed_hosts must not be empty")
    need(cfg.prep.max_scryfall_prints > cfg.prep.min_scryfall_prints,
         "prep.max_scryfall_prints must be > prep.min_scryfall_prints")
    need(cfg.prep.max_decompressed_bytes > 0, "prep.max_decompressed_bytes must be > 0")
    order = cfg.stages.order
    need(not cfg.approve.enabled or "approve" in order,
         "approve.enabled=true but 'approve' is not in stages.order (approval would be bypassed)")
    missing_live = [s for s in LIVE_CHECK_STAGES if s not in order]
    need(not missing_live or cfg.stages.allow_partial_promote,
         f"stages.order lacks {missing_live}: a promotion would never be loaded and health-checked; "
         "set stages.allow_partial_promote=true only for rehearsals")
    need(cfg.health.timeout_s > 0 and cfg.health.poll_interval_s > 0,
         "health.timeout_s and health.poll_interval_s must be > 0")
    need(cfg.approve.wait_minutes >= 0, "approve.wait_minutes must be >= 0")
    f = cfg.fetch
    need(0 < f.scryfall_min_bytes < f.scryfall_max_bytes, "fetch.scryfall_min_bytes < scryfall_max_bytes")
    need(0 < f.mtgish_min_bytes < f.mtgish_max_bytes, "fetch.mtgish_min_bytes < mtgish_max_bytes")
    ua = cfg.upstream.user_agent
    need(bool(ua) and "@" not in ua,
         "upstream.user_agent must be set and generic (no e-mail address or personal name)")
    pin = cfg.upstream.mtgish_pin_sha
    need(pin is None or (len(pin) == 40 and all(c in "0123456789abcdef" for c in pin)),
         "upstream.mtgish_pin_sha must be a full 40-hex commit sha or null")
    errors.extend(_validate_order(cfg.stages.order))
    if errors:
        raise ConfigError("invalid configuration:\n  - " + "\n  - ".join(errors))


def _validate_order(order: list[str]) -> list[str]:
    errors: list[str] = []
    known = set(DEFAULT_STAGE_ORDER)
    seen: set[str] = set()
    for name in order:
        if name in seen:
            errors.append(f"stages.order: duplicate stage '{name}'")
        seen.add(name)
        if name not in known and ":" not in name:
            errors.append(f"stages.order: unknown stage '{name}' "
                          "(built-ins: " + ", ".join(DEFAULT_STAGE_ORDER) + "; custom: 'module:Class')")
    missing = [s for s in ESSENTIAL_STAGES if s not in order]
    if missing:
        errors.append("stages.order: essential stage(s) missing: " + ", ".join(missing))
    else:
        positions = [order.index(s) for s in ESSENTIAL_STAGES]
        if positions != sorted(positions):
            errors.append("stages.order: essential stages must keep their order: "
                          + " -> ".join(ESSENTIAL_STAGES))
        builtin = [s for s in order if s in known]
        if [s for s in DEFAULT_STAGE_ORDER if s in builtin] != builtin:
            errors.append("stages.order: built-in stages must keep their relative order: "
                          + " -> ".join(DEFAULT_STAGE_ORDER))
    return errors


def load_config(path: Path | None, environ: Mapping[str, str] | None = None) -> Config:
    """Defaults <- JSON file (if given) <- CARD_UPDATE__* env overrides; validated."""
    environ = os.environ if environ is None else environ
    merged: dict[str, dict[str, Any]] = {name: {} for name in _SECTIONS}
    source = "<defaults>"
    if path is not None:
        path = Path(path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ConfigError(f"config file not found: {path}") from None
        except (OSError, ValueError) as exc:
            raise ConfigError(f"cannot read config {path}: {exc}") from None
        _merge(merged, raw, str(path))
        source = str(path)
    _merge(merged, _env_overrides(environ), "environment")

    sections = {name: _build_section(name, cls, copy.deepcopy(merged[name]))
                for name, cls in _SECTIONS.items()}
    paths = _resolve_paths(sections.pop("paths"), sections["approve"], environ)
    cfg = Config(paths=paths, source=source, **sections)
    _validate(cfg)
    return cfg
