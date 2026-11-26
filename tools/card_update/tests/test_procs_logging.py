from __future__ import annotations

import io
import logging
import sys

import pytest

from card_update.logging_setup import close_logger, make_run_logger, stage_logger
from card_update.manifest import Manifest, ManifestError, StageRecord, load_manifest
from card_update.procs import CommandTimeout, SubprocessRunner


def test_runner_streams_output_and_returns_code(tmp_path):
    buf = io.StringIO()
    log = make_run_logger("t1", tmp_path / "run.log", stream=buf)
    res = SubprocessRunner(log).run(
        [sys.executable, "-c", "import sys; print('hello'); print('err', file=sys.stderr); sys.exit(3)"],
        cwd=tmp_path, timeout_s=60, label="child")
    close_logger(log)
    assert res.returncode == 3
    assert "hello" in res.tail and "err" in res.tail
    text = (tmp_path / "run.log").read_text(encoding="utf-8")
    assert "[child] hello" in text and "run=t1" in text


def test_runner_kills_on_timeout(tmp_path):
    log = make_run_logger("t2", None, stream=io.StringIO())
    with pytest.raises(CommandTimeout):
        SubprocessRunner(log).run([sys.executable, "-c", "import time; print('x', flush=True); time.sleep(30)"],
                                  cwd=tmp_path, timeout_s=1, label="slow")
    close_logger(log)


def test_log_lines_are_iso_utc_with_stage_prefix():
    buf = io.StringIO()
    log = make_run_logger("rid", None, stream=buf)
    stage_logger(log, "fetch").info("downloaded %d", 5)
    close_logger(log)
    line = buf.getvalue().strip()
    assert line[:4].isdigit() and line[10] == "T" and line[23] == "Z"
    assert "run=rid | [fetch] downloaded 5" in line


def test_manifest_round_trip(tmp_path):
    m = Manifest(run_id="r", workdir=str(tmp_path), created_utc="2026-11-26T02:30:00Z")
    m.record(StageRecord(name="check", status="ok", outputs={"a": 1}))
    m.record(StageRecord(name="check", status="failed"))          # re-record replaces
    m.artifacts["x"] = {"y": 2}
    m.save(tmp_path)
    back = load_manifest(tmp_path)
    assert back.stage_status("check") == "failed" and back.artifacts == {"x": {"y": 2}}


def test_missing_manifest_is_an_error(tmp_path):
    with pytest.raises(ManifestError):
        load_manifest(tmp_path)


def test_logger_has_no_global_side_effects():
    log = make_run_logger("iso", None, stream=io.StringIO())
    assert log.propagate is False
    assert not logging.getLogger().handlers or all(
        h not in logging.getLogger().handlers for h in log.handlers)
    close_logger(log)
