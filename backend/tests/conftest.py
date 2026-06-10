"""Shared test guards.

Several fixtures mutate the database destructively (TRUNCATE userdecks; rename the
combo tables aside and back). Those are safe against a local dev database but would
wipe/disrupt a real one if DATABASE_URL ever pointed at prod. This session-scoped,
autouse guard aborts the whole run unless the target is clearly a safe destructive
target: a local host, a database whose name ends in `_test`, or an explicit opt-in
(DECKDOCTOR_ALLOW_DESTRUCTIVE_TESTS=1).
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import config  # noqa: E402

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", ""}


def assert_safe_destructive_db() -> None:
    """Raise unless DATABASE_URL is a safe target for destructive test mutation."""
    dsn = urlparse(config.DATABASE_URL)
    host = (dsn.hostname or "").lower()
    dbname = (dsn.path or "").lstrip("/")
    if host in _LOCAL_HOSTS:
        return
    if dbname.endswith("_test"):
        return
    if os.environ.get("DECKDOCTOR_ALLOW_DESTRUCTIVE_TESTS") == "1":
        return
    raise RuntimeError(
        f"Refusing destructive tests against non-local DB '{host}/{dbname}'. "
        "Point DATABASE_URL at a local or *_test database, or set "
        "DECKDOCTOR_ALLOW_DESTRUCTIVE_TESTS=1.")


@pytest.fixture(scope="session", autouse=True)
def _guard_destructive_tests():
    try:
        assert_safe_destructive_db()
    except RuntimeError as e:
        pytest.exit(str(e), returncode=2)
    yield
