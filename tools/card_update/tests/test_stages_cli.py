"""Stage-level units (conversion, enrich threshold, upstream validation) and the CLI
commands (exit codes, check/status/gc/init)."""

from __future__ import annotations

import gzip
import io
import json

import pytest

from card_update.cli import main
from card_update.config import load_config
from card_update.stages.base import StageError
from card_update.stages.prep import convert_to_array
from card_update.upstream import UpstreamError, probe_upstream, scryfall_format

import harness as H


# ── prep conversion ─────────────────────────────────────────────────────────

def test_convert_streams_jsonl_gz_and_applies_the_filter(tmp_path):
    src = tmp_path / "b.jsonl.gz"
    src.write_bytes(H.gz_bytes())
    out = tmp_path / "a.json"
    stats = convert_to_array(src, "jsonl.gz", out, keep=lambda c: c.get("lang") == "en")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert stats == {"prints": 14, "kept": 13} and len(data) == 13
    assert all(c["lang"] == "en" for c in data)


def test_convert_rejects_a_truncated_line(tmp_path):
    src = tmp_path / "b.jsonl.gz"
    with gzip.open(src, "wt", encoding="utf-8") as fh:
        fh.write('{"id": "a"}\n{"id": "b", "na')
    with pytest.raises(StageError) as ei:
        convert_to_array(src, "jsonl.gz", tmp_path / "a.json", keep=lambda c: True)
    assert "line 2" in str(ei.value)
    assert not (tmp_path / "a.json").exists() and not (tmp_path / "a.json.part").exists()


def test_scryfall_format_detection():
    assert scryfall_format("https://x/default-cards-1.jsonl.gz") == "jsonl.gz"
    assert scryfall_format("https://x/default-cards-1.jsonl") == "jsonl"
    for bad in ("https://x/default-cards-1.json", "https://x/default-cards.json.gz", "https://x/d.zip"):
        with pytest.raises(UpstreamError):          # arrays would be loaded whole: streamed JSONL only
            scryfall_format(bad)


def test_convert_caps_decompressed_bytes(tmp_path):
    src = tmp_path / "b.jsonl.gz"
    src.write_bytes(H.gz_bytes())
    with pytest.raises(StageError) as ei:
        convert_to_array(src, "jsonl.gz", tmp_path / "a.json", keep=lambda c: True, max_bytes=2000)
    assert "max_decompressed_bytes" in str(ei.value) and not (tmp_path / "a.json").exists()


def test_convert_caps_line_count(tmp_path):
    src = tmp_path / "b.jsonl.gz"
    src.write_bytes(H.gz_bytes())
    with pytest.raises(StageError) as ei:
        convert_to_array(src, "jsonl.gz", tmp_path / "a.json", keep=lambda c: True, max_lines=5)
    assert "max_scryfall_prints" in str(ei.value)


# ── upstream probe ──────────────────────────────────────────────────────────

class _Meta:
    def __init__(self, bulk, head):
        self.bulk, self.head = bulk, head

    def get_json(self, url, *, accept="application/json"):
        return self.bulk if "scryfall" in url else self.head


def test_probe_rejects_wrong_bulk_type():
    with pytest.raises(UpstreamError):
        probe_upstream(load_config(None, {}), _Meta({"type": "oracle_cards"}, {"sha": "a" * 40}))


def test_probe_rejects_bad_sha():
    bulk = {"type": "default_cards", "updated_at": "x", "jsonl_download_uri": "https://d/x.jsonl.gz"}
    with pytest.raises(UpstreamError):
        probe_upstream(load_config(None, {}), _Meta(bulk, {"sha": "not-a-sha"}))


def test_probe_uses_pin_without_asking_github():
    bulk = {"type": "default_cards", "updated_at": "x", "jsonl_download_uri": "https://d/x.jsonl.gz",
            "compressed_size": 5}
    cfg = load_config(None, {"CARD_UPDATE__UPSTREAM__MTGISH_PIN_SHA": "c" * 40})
    up = probe_upstream(cfg, _Meta(bulk, None))
    assert up["mtgish"] == {"sha": "c" * 40, "pinned": True,
                            "data_url": f"https://raw.githubusercontent.com/i5jb/mtgish/{'c' * 40}/data/mtgish.lines.json",
                            "license_url": f"https://raw.githubusercontent.com/i5jb/mtgish/{'c' * 40}/LICENSE"}
    assert up["scryfall"]["size"] == 5 and up["scryfall"]["format"] == "jsonl.gz"


# ── enrich fails loudly instead of writing partial data ─────────────────────

def test_enrich_batch_failure_above_threshold_fails_the_run(h):
    h.fetcher.fail = {"cards/collection"}
    code, out = h.main("run")
    assert code == 1 and "collection batches failed" in out
    assert "Lightning Bolt" not in h.live_names()


def test_enrich_tolerates_failures_within_threshold(h):
    h.fetcher.fail = {"cards/collection"}
    h.overrides = {"enrich": {"max_error_batches": 5}, "gates": {"min_cards": 5, "min_land_meta_coverage": 0.0}}
    code, out = h.main("run", "--no-promote")
    assert code == 0, out


# ── CLI ─────────────────────────────────────────────────────────────────────

def test_config_flag_works_before_and_after_the_command(h):
    cfg = str(h.config_path())
    for argv in (["--config", cfg, "status", "--offline"], ["status", "--offline", "--config", cfg]):
        out = io.StringIO()
        main(argv, environ={}, clock=h.clock, services=h.services_builder(), stream=out)
        assert "seed-1" in out.getvalue()


def test_bad_config_exits_2(tmp_path):
    p = tmp_path / "c.json"
    p.write_text('{"gates": {"min_cards": "x"}}', encoding="utf-8")
    assert main(["--config", str(p), "status", "--offline"], environ={}, stream=io.StringIO()) == 2


def test_usage_error_exits_2():
    assert main(["run", "--bogus"], environ={}, stream=io.StringIO()) == 2


def test_check_reports_update_and_exits_0_without_writing(h):
    code, out = h.main("check")
    assert code == 0 and "UPDATE AVAILABLE" in out and "mtgish aaaaaaaaaaaa -> bbbbbbbbbbbb" in out
    assert h.run_dirs() == []


def test_check_reports_nothing_new(h):
    h.state_file.write_text(json.dumps({"mtgish_sha": H.NEW_SHA, "scryfall_updated_at": H.UPDATED_AT}),
                            encoding="utf-8")
    code, out = h.main("check")
    assert code == 0 and "NOTHING NEW" in out


def test_check_network_failure_exits_1(h):
    h.fetcher.fail = {"api.scryfall.com"}
    assert h.main("check")[0] == 1


def test_status_is_stale_without_a_recent_success(h):
    code, out = h.main("status", "--offline")
    assert code == 1 and "STALE" in out


def test_status_ok_after_success_and_shows_pending_upstream(h):
    assert h.main("run")[0] == 0
    code, out = h.main("status")
    assert code == 0, out
    assert "verdict:               OK" in out and "pending upstream:      none" in out


def test_status_flags_failures(h):
    h.overrides = {"gates": {"min_cards": 5, "sentinels": ["Black Lotus"]}}
    h.main("run")
    code, out = h.main("status", "--offline")
    assert "consecutive failures:  1 (last: verify" in out


def test_gc_applies_retention(h):
    h.overrides = {"retention": {"keep_runs": 1}}
    h.main("run", "--no-promote")
    h.clock.advance(60)
    h.main("run", "--no-promote")
    assert len(h.run_dirs()) == 2
    assert h.main("gc")[0] == 0
    assert len(h.run_dirs()) == 1


def test_init_seeds_live_files_once(h, tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "cards.json").write_text('[{"id": "x"}]', encoding="utf-8")
    (seed / "land_meta.json").write_text("{}", encoding="utf-8")
    h.live_cards.unlink()
    (h.live_cards.parent / "land_meta.json").unlink()
    h.state_file.unlink()
    h.overrides = {"paths": {"seed_cards": str(seed / "cards.json"),
                             "seed_land_meta": str(seed / "land_meta.json")}}
    code, out = h.main("init", "--mtgish-sha", "d" * 40)
    assert code == 0, out
    assert h.live_cards.read_text(encoding="utf-8") == '[{"id": "x"}]'
    st = h.state()
    assert st["mtgish_sha"] == "d" * 40 and st["current_release_id"].startswith("seed-")
    code, out = h.main("init")
    assert code == 0 and "already initialised" in out


def test_init_rejects_short_sha(h, tmp_path):
    h.live_cards.unlink()
    assert h.main("init", "--mtgish-sha", "abc")[0] == 2
