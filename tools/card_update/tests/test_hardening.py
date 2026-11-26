"""Findings 5, 14, 15 and SIGTERM handling: host allowlist (incl. redirects), JSON size
cap, secret redaction in child output, process-group kill, SIGTERM-once."""

from __future__ import annotations

import io
import logging
import os
import sys
import time
import urllib.request

import pytest

from card_update.cli import Terminated, _SigtermOnce
from card_update.http import FetchError, UrllibFetcher, _AllowlistRedirects, host_allowed
from card_update.logging_setup import close_logger, make_run_logger
from card_update.procs import CommandTimeout, SubprocessRunner, redact

ALLOW = ("scryfall.com", "scryfall.io", "api.github.com", "raw.githubusercontent.com")


@pytest.mark.parametrize("url,ok", [
    ("https://api.scryfall.com/bulk-data/default-cards", True),
    ("https://data.scryfall.io/default-cards/x.jsonl.gz", True),
    ("https://raw.githubusercontent.com/i5jb/mtgish/x/LICENSE", True),
    ("http://api.scryfall.com/x", False),                  # not https
    ("https://evilscryfall.com/x", False),                 # suffix trick
    ("https://scryfall.com.evil.net/x", False),
    ("https://169.254.169.254/latest/meta-data", False),   # SSRF target
    ("https://localhost:8002/admin/reload", False),
])
def test_host_allowlist(url, ok):
    assert host_allowed(url, ALLOW) is ok


def _fetcher(clock, opener=None, **kw):
    return UrllibFetcher(user_agent="UA", timeout_s=5, retries=0, backoff_s=0, backoff_max_s=0,
                         min_interval_s=0.1, clock=clock, log=logging.getLogger("t"),
                         opener=opener or (lambda req, timeout: (_ for _ in ()).throw(AssertionError("sent"))),
                         allowed_hosts=ALLOW, **kw)


def test_request_to_a_non_allowlisted_host_is_refused_before_sending(clock):
    with pytest.raises(FetchError) as ei:
        _fetcher(clock).get_json("https://internal.example/secret")
    assert "allowed_hosts" in str(ei.value)


def test_redirect_off_the_allowlist_is_refused():
    handler = _AllowlistRedirects(ALLOW)
    req = urllib.request.Request("https://data.scryfall.io/x.jsonl.gz")
    with pytest.raises(FetchError):
        handler.redirect_request(req, None, 302, "Found", {}, "http://10.0.0.5/x")
    ok = handler.redirect_request(req, None, 302, "Found", {}, "https://cdn.scryfall.io/x.jsonl.gz")
    assert ok.full_url == "https://cdn.scryfall.io/x.jsonl.gz"


def test_json_responses_are_size_capped(clock):
    class Resp(io.BytesIO):
        status, headers = 200, {}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()
    f = _fetcher(clock, opener=lambda req, timeout: Resp(b"[" + b"1," * 600 + b"1]"), max_json_bytes=1000)
    with pytest.raises(FetchError) as ei:
        f.get_json("https://api.scryfall.com/x")
    assert "larger than" in str(ei.value)


@pytest.mark.parametrize("line,secret", [
    ("loaded into postgresql://deckdoctor:s3cr3t@localhost/deckdoctor", "s3cr3t"),
    ("dsn: host=localhost dbname=deckdoctor password=s3cr3t user=x", "s3cr3t"),
    ("PASSWORD = 's3 cr3t'", "s3 cr3t"),
])
def test_child_output_is_redacted(line, secret):
    assert secret not in redact(line)


def test_runner_logs_redacted_child_output(tmp_path):
    buf = io.StringIO()
    log = make_run_logger("r", None, stream=buf)
    SubprocessRunner(log).run([sys.executable, "-c", "print('url postgresql://u:hunter2@h/db')"],
                              cwd=tmp_path, timeout_s=60, label="c")
    close_logger(log)
    assert "hunter2" not in buf.getvalue() and "u:***@h/db" in buf.getvalue()


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX")
def test_timeout_kills_grandchildren_too(tmp_path):
    marker = tmp_path / "grandchild-alive"
    script = (f"import subprocess,sys; subprocess.Popen([sys.executable,'-c',"
              f"\"import time,pathlib; time.sleep(3); pathlib.Path(r'{marker}').write_text('x')\"]); "
              f"import time; time.sleep(60)")
    log = make_run_logger("g", None, stream=io.StringIO())
    with pytest.raises(CommandTimeout):
        SubprocessRunner(log).run([sys.executable, "-c", script], cwd=tmp_path, timeout_s=1, label="g")
    close_logger(log)
    time.sleep(4)
    assert not marker.exists()                  # the grandchild died with the group


def test_first_sigterm_raises_later_ones_are_ignored():
    out = io.StringIO()
    h = _SigtermOnce(out)
    with pytest.raises(Terminated):
        h(15, None)
    h(15, None)                                 # second: ignored so the revert can finish
    assert "ignored" in out.getvalue()
