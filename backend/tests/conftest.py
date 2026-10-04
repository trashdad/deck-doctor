"""Shared test guards.

Several fixtures mutate the database destructively (TRUNCATE userdecks; rename the
combo tables aside and back). This session-scoped, autouse guard aborts the whole run
unless DATABASE_URL names a database that is clearly a throwaway:

  * its name ends in `_test` (e.g. `deckdoctor_test`), or
  * DECKDOCTOR_ALLOW_DESTRUCTIVE_TESTS=1 is set explicitly.

"Local host" is NOT a safety signal: on the prod VPS (simtrack) the live database is
on localhost and named `deckdoctor`. A database named exactly `deckdoctor` is always
refused without the opt-in. Pure tests never connect, so any `*_test` DSN works for
them (e.g. DATABASE_URL=postgresql://x@localhost/deckdoctor_test).
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import config  # noqa: E402

PROD_DB_NAME = "deckdoctor"
OPT_IN_ENV = "DECKDOCTOR_ALLOW_DESTRUCTIVE_TESTS"


def assert_safe_destructive_db() -> None:
    """Raise unless DATABASE_URL is a safe target for destructive test mutation."""
    dsn = urlparse(config.DATABASE_URL)
    host = (dsn.hostname or "").lower()
    dbname = (dsn.path or "").lstrip("/").split("?")[0]
    if os.environ.get(OPT_IN_ENV) == "1":
        return
    if dbname != PROD_DB_NAME and dbname.endswith("_test"):
        return
    raise RuntimeError(
        f"Refusing destructive tests against DB '{host}/{dbname}': only a *_test database "
        f"may be mutated (and '{PROD_DB_NAME}' never, without the opt-in). Point "
        f"DATABASE_URL at e.g. .../deckdoctor_test, or set {OPT_IN_ENV}=1 on a box "
        "with no production data.")


@pytest.fixture(scope="session", autouse=True)
def _guard_destructive_tests():
    try:
        assert_safe_destructive_db()
    except RuntimeError as e:
        pytest.exit(str(e), returncode=2)
    yield
