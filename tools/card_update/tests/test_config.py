from __future__ import annotations

import json
from pathlib import Path

import pytest

from card_update.config import DEFAULT_STAGE_ORDER, ConfigError, load_config


def _write(tmp_path: Path, obj) -> Path:
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


def test_defaults_resolve_paths_under_app_dir():
    cfg = load_config(None, environ={})
    app = Path("/opt/deck-doctor")
    assert cfg.paths.app_dir == app
    assert cfg.paths.card_data_dir == app / "card-data"
    assert cfg.paths.live_cards == app / "card-data" / "current" / "cards.json"
    assert cfg.paths.live_land_meta == app / "card-data" / "current" / "land_meta.json"
    assert cfg.paths.live_scores == app / "data" / "scores.sqlite"
    assert cfg.paths.lock_file == app / "data" / ".pipeline.lock"
    assert cfg.stages.order == list(DEFAULT_STAGE_ORDER)
    assert cfg.approve.enabled is False
    assert cfg.retention.keep_releases == 3 and cfg.retention.keep_runs == 5


def test_user_agent_is_generic():
    ua = load_config(None, environ={}).upstream.user_agent
    assert ua == "DeckDoctor-CardUpdate/1.0 (+https://simmander.app/deck-doctor)"
    assert "@" not in ua


def test_live_paths_follow_the_api_env_vars():
    cfg = load_config(None, environ={"SIMMANDER_CARDS": "/x/cards.json",
                                     "SIMMANDER_LAND_META": "/x/land_meta.json"})
    assert cfg.paths.live_cards == Path("/x/cards.json")
    assert cfg.paths.live_land_meta == Path("/x/land_meta.json")


def test_file_values_override_defaults(tmp_path):
    p = _write(tmp_path, {"paths": {"app_dir": str(tmp_path)}, "gates": {"min_cards": 10}})
    cfg = load_config(p, environ={})
    assert cfg.paths.app_dir == tmp_path
    assert cfg.paths.card_data_dir == tmp_path / "card-data"
    assert cfg.gates.min_cards == 10


def test_env_overrides_beat_the_file(tmp_path):
    p = _write(tmp_path, {"gates": {"min_cards": 10}})
    cfg = load_config(p, environ={"CARD_UPDATE__GATES__MIN_CARDS": "42",
                                  "CARD_UPDATE__APPROVE__ENABLED": "true"})
    assert cfg.gates.min_cards == 42
    assert cfg.approve.enabled is True


@pytest.mark.parametrize("obj,needle", [
    ({"gatez": {}}, "unknown section"),
    ({"gates": {"min_cardz": 1}}, "unknown key"),
    ({"gates": {"min_cards": "many"}}, "gates.min_cards"),
    ({"gates": {"min_count_ratio": 1.5}}, "min_count_ratio"),
    ({"gates": {"max_count_ratio": 0.9}}, "max_count_ratio"),
    ({"enrich": {"batch_size": 76}}, "batch_size"),
    ({"enrich": {"interval_s": 0.05}}, "interval_s"),
    ({"retention": {"keep_releases": 0}}, "keep_releases"),
    ({"http": {"retries": -1}}, "retries"),
    ({"approve": {"enabled": "yes"}}, "approve.enabled"),
    ({"stages": {"order": ["check", "fetch", "prep", "build", "promote", "verify"]}}, "order"),
    ({"stages": {"order": ["check", "fetch", "prep", "build", "promote"]}}, "verify"),
    ({"stages": {"order": ["check", "bogus", "fetch", "prep", "build", "verify", "promote"]}}, "bogus"),
    ({"stages": {"order": ["check", "check", "fetch", "prep", "build", "verify", "promote"]}}, "duplicate"),
    ({"upstream": {"user_agent": "me <me@example.com>"}}, "user_agent"),
])
def test_invalid_config_is_rejected(tmp_path, obj, needle):
    with pytest.raises(ConfigError) as ei:
        load_config(_write(tmp_path, obj), environ={})
    assert needle in str(ei.value)


def test_unparseable_file_is_a_config_error(tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text("{nope", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(p, environ={})


def test_missing_file_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "absent.json", environ={})


def test_bad_env_override_is_a_config_error():
    with pytest.raises(ConfigError):
        load_config(None, environ={"CARD_UPDATE__NOPE__X": "1"})


def test_optional_stages_can_be_plugged_out_and_custom_ones_in(tmp_path):
    order = ["check", "fetch", "prep", "build", "verify", "mypkg.mod:MyStage", "promote", "rebuild", "health"]
    cfg = load_config(_write(tmp_path, {"stages": {"order": order}}), environ={})
    assert cfg.stages.order == order


@pytest.mark.parametrize("missing", ["rebuild", "health"])
def test_promote_without_rebuild_or_health_is_rejected(tmp_path, missing):
    order = [s for s in DEFAULT_STAGE_ORDER if s != missing]
    with pytest.raises(ConfigError) as ei:
        load_config(_write(tmp_path, {"stages": {"order": order}}), environ={})
    assert "allow_partial_promote" in str(ei.value)


def test_partial_promote_must_be_explicit(tmp_path):
    order = ["check", "fetch", "prep", "build", "verify", "promote"]
    cfg = load_config(_write(tmp_path, {"stages": {"order": order, "allow_partial_promote": True}}), environ={})
    assert cfg.stages.allow_partial_promote is True


def test_approval_enabled_without_the_stage_is_rejected(tmp_path):
    order = [s for s in DEFAULT_STAGE_ORDER if s != "approve"]
    with pytest.raises(ConfigError) as ei:
        load_config(_write(tmp_path, {"stages": {"order": order}, "approve": {"enabled": True}}), environ={})
    assert "approval would be bypassed" in str(ei.value)


def test_default_host_allowlist_covers_the_sources():
    hosts = load_config(None, environ={}).http.allowed_hosts
    assert {"scryfall.com", "scryfall.io", "api.github.com", "raw.githubusercontent.com"} <= set(hosts)


def test_example_config_is_valid():
    example = Path(__file__).resolve().parents[1] / "card_update.example.json"
    cfg = load_config(example, environ={})
    assert cfg.stages.order == list(DEFAULT_STAGE_ORDER)
    from dataclasses import asdict, replace
    assert asdict(replace(cfg, source="")) == asdict(replace(load_config(None, environ={}), source=""))
