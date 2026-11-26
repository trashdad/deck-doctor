"""Injectable HTTP client (stdlib urllib): retries, backoff, timeouts, per-host
throttle, size/sha256 checks and atomic ``.part -> rename`` downloads.

Stages depend on the ``Fetcher`` protocol only, so tests pass a fake and the
production transport is never touched without network.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

from card_update.clock import Clock
from card_update.fsutil import fsync_dir

_CHUNK = 1 << 20


class FetchError(Exception):
    """A request failed for good (after bounded retries, or a non-retryable error)."""


class _Retryable(Exception):
    """Internal: transient failure worth another attempt."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@dataclass(frozen=True)
class DownloadResult:
    url: str
    path: Path
    size: int
    sha256: str


class Fetcher(Protocol):
    def get_json(self, url: str, *, accept: str = "application/json") -> Any: ...

    def post_json(self, url: str, payload: Any) -> Any: ...

    def get_text(self, url: str, *, max_bytes: int = 1_000_000) -> str: ...

    def download(self, url: str, dest: Path, *, expected_size: int | None = None,
                 expected_sha256: str | None = None, min_size: int = 0,
                 max_size: int | None = None) -> DownloadResult: ...


Opener = Callable[[urllib.request.Request, float], Any]


def host_allowed(url: str, allowed_hosts: Sequence[str] | None) -> bool:
    """https + host equal to (or a subdomain of) an allowlist entry; None = no restriction."""
    if allowed_hosts is None:
        return True
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    return parts.scheme == "https" and any(host == h or host.endswith("." + h) for h in allowed_hosts)


class _AllowlistRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: Sequence[str] | None) -> None:
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        if not host_allowed(newurl, self.allowed_hosts):
            raise FetchError(f"refusing redirect from {req.full_url} to {newurl} "
                             "(not https or host not in http.allowed_hosts)")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def make_opener(allowed_hosts: Sequence[str] | None) -> Opener:
    opener = urllib.request.build_opener(_AllowlistRedirects(allowed_hosts))

    def open_(req: urllib.request.Request, timeout: float) -> Any:
        return opener.open(req, timeout=timeout)
    return open_


class UrllibFetcher:
    def __init__(self, *, user_agent: str, timeout_s: float, retries: int, backoff_s: float,
                 backoff_max_s: float, min_interval_s: float, clock: Clock,
                 log: logging.Logger | logging.LoggerAdapter,
                 opener: Opener | None = None, allowed_hosts: Sequence[str] | None = None,
                 max_json_bytes: int = 20_000_000) -> None:
        self.user_agent = user_agent
        self.timeout_s = timeout_s
        self.retries = retries
        self.backoff_s = backoff_s
        self.backoff_max_s = backoff_max_s
        self.min_interval_s = min_interval_s
        self.clock = clock
        self.log = log
        self.allowed_hosts = tuple(allowed_hosts) if allowed_hosts is not None else None
        self.max_json_bytes = max_json_bytes
        self._opener = opener or make_opener(self.allowed_hosts)
        self._last_request: dict[str, float] = {}

    # ── public API ───────────────────────────────────────────────────────────
    def get_json(self, url: str, *, accept: str = "application/json") -> Any:
        body = self._with_retries("GET", url, lambda: self._read(url, None, {"Accept": accept},
                                                                  self.max_json_bytes))
        return self._parse_json(url, body)

    def post_json(self, url: str, payload: Any) -> Any:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        body = self._with_retries("POST", url, lambda: self._read(url, data, headers, self.max_json_bytes))
        return self._parse_json(url, body)

    def get_text(self, url: str, *, max_bytes: int = 1_000_000) -> str:
        body = self._with_retries(
            "GET", url, lambda: self._read(url, None, {"Accept": "text/plain"}, max_bytes))
        return body.decode("utf-8", errors="replace")

    def download(self, url: str, dest: Path, *, expected_size: int | None = None,
                 expected_sha256: str | None = None, min_size: int = 0,
                 max_size: int | None = None) -> DownloadResult:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        try:
            size, digest = self._with_retries(
                "DOWNLOAD", url,
                lambda: self._stream_to(url, part, expected_size, expected_sha256, max_size))
            if size < min_size:
                raise FetchError(f"{url}: downloaded {size:,} bytes, below the configured "
                                 f"min of {min_size:,} — upstream file looks truncated or wrong")
            os.replace(part, dest)
            fsync_dir(dest.parent)
        finally:
            if part.exists():
                part.unlink()
        self.log.info("downloaded %s -> %s (%s bytes, sha256 %s)", url, dest, f"{size:,}", digest)
        return DownloadResult(url=url, path=dest, size=size, sha256=digest)

    # ── internals ────────────────────────────────────────────────────────────
    def _parse_json(self, url: str, body: bytes) -> Any:
        try:
            return json.loads(body)
        except ValueError as exc:
            raise FetchError(f"{url}: response is not JSON ({exc})") from None

    def _throttle(self, url: str) -> None:
        host = urllib.parse.urlsplit(url).hostname or ""
        last = self._last_request.get(host)
        if last is not None:
            wait = self.min_interval_s - (self.clock.monotonic() - last)
            if wait > 0:
                self.clock.sleep(wait)
        self._last_request[host] = self.clock.monotonic()

    def _request(self, url: str, data: bytes | None, headers: dict[str, str]) -> urllib.request.Request:
        if not host_allowed(url, self.allowed_hosts):
            raise FetchError(f"refusing {url}: not https or host not in http.allowed_hosts")
        hdrs = {"User-Agent": self.user_agent, **headers}
        return urllib.request.Request(url, data=data, headers=hdrs,
                                      method="POST" if data is not None else "GET")

    def _open(self, req: urllib.request.Request) -> Any:
        self._throttle(req.full_url)
        try:
            return self._opener(req, self.timeout_s)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                retry_after = _retry_after(exc.headers)
                raise _Retryable(f"HTTP {exc.code}", retry_after) from None
            raise FetchError(f"{req.full_url}: HTTP {exc.code} {exc.reason}") from None

    def _read(self, url: str, data: bytes | None, headers: dict[str, str],
              max_bytes: int | None = None) -> bytes:
        with self._open(self._request(url, data, headers)) as resp:
            body = resp.read() if max_bytes is None else resp.read(max_bytes + 1)
        if max_bytes is not None and len(body) > max_bytes:
            raise FetchError(f"{url}: response larger than {max_bytes:,} bytes")
        return body

    def _stream_to(self, url: str, part: Path, expected_size: int | None,
                   expected_sha256: str | None, max_size: int | None) -> tuple[int, str]:
        h = hashlib.sha256()
        size = 0
        with self._open(self._request(url, None, {"Accept": "*/*"})) as resp, open(part, "wb") as out:
            declared = (resp.headers or {}).get("Content-Length")
            if declared is not None and max_size is not None and int(declared) > max_size:
                raise FetchError(f"{url}: Content-Length {int(declared):,} exceeds the configured "
                                 f"max of {max_size:,} bytes")
            while True:
                chunk = resp.read(_CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if max_size is not None and size > max_size:
                    raise FetchError(f"{url}: download exceeds the configured max of "
                                     f"{max_size:,} bytes — refusing")
                h.update(chunk)
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        if expected_size is not None and size != expected_size:
            raise _Retryable(f"size {size:,} != expected {expected_size:,} bytes")
        digest = h.hexdigest()
        if expected_sha256 is not None and digest != expected_sha256:
            raise _Retryable(f"sha256 {digest} != expected {expected_sha256}")
        return size, digest

    def _with_retries(self, verb: str, url: str, fn: Callable[[], Any]) -> Any:
        attempts = self.retries + 1
        last = ""
        for attempt in range(attempts):
            try:
                return fn()
            except _Retryable as exc:
                last, retry_after = str(exc), exc.retry_after
            except (urllib.error.URLError, http.client.HTTPException, ConnectionError,
                    TimeoutError) as exc:
                last, retry_after = f"{type(exc).__name__}: {exc}", None
            if attempt + 1 >= attempts:
                break
            delay = min(self.backoff_s * (2 ** attempt), self.backoff_max_s)
            if retry_after is not None:
                delay = max(delay, min(retry_after, self.backoff_max_s))
            self.log.warning("%s %s failed (%s); retry %d/%d in %.0fs",
                             verb, url, last, attempt + 1, self.retries, delay)
            self.clock.sleep(delay)
        raise FetchError(f"{verb} {url} failed after {attempts} attempt(s): {last}")


def _retry_after(headers: Any) -> float | None:
    try:
        value = headers.get("Retry-After") if headers is not None else None
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
