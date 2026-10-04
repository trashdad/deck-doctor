"""The destructive-test guard (tests/conftest.py::assert_safe_destructive_db).

On simtrack the PROD database is on localhost and named `deckdoctor`, so "local host"
is not a safety signal. Only a `*_test` database — or the explicit opt-in — may be
mutated, and a database named exactly `deckdoctor` is refused without the opt-in.
"""

import pytest

from app import config
from tests.conftest import assert_safe_destructive_db

OPT_IN = "DECKDOCTOR_ALLOW_DESTRUCTIVE_TESTS"


def _check(monkeypatch, dsn, opt_in=False):
    monkeypatch.setattr(config, "DATABASE_URL", dsn)
    if opt_in:
        monkeypatch.setenv(OPT_IN, "1")
    else:
        monkeypatch.delenv(OPT_IN, raising=False)
    assert_safe_destructive_db()


@pytest.mark.parametrize("dsn", [
    "postgresql://deckdoctor:pw@127.0.0.1:5432/deckdoctor",      # prod on simtrack
    "postgresql://deckdoctor:pw@localhost:5432/deckdoctor",
    "postgresql://deckdoctor:pw@db.example.com:5432/deckdoctor",
    "postgresql://u:pw@localhost:5432/deckdoctor_verify",         # local but not *_test
    "postgresql://u:pw@db.example.com:5432/scratch",
])
def test_refuses_anything_but_a_test_db(monkeypatch, dsn):
    with pytest.raises(RuntimeError):
        _check(monkeypatch, dsn)


@pytest.mark.parametrize("dsn", [
    "postgresql://u:pw@127.0.0.1:5432/deckdoctor_test",
    "postgresql://u:pw@db.example.com:5432/deckdoctor_test",
])
def test_allows_test_databases(monkeypatch, dsn):
    _check(monkeypatch, dsn)


def test_opt_in_allows_even_deckdoctor(monkeypatch):
    _check(monkeypatch, "postgresql://u:pw@localhost:5432/deckdoctor", opt_in=True)


def test_opt_in_must_be_exactly_one(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://u:pw@localhost:5432/deckdoctor")
    monkeypatch.setenv(OPT_IN, "true")
    with pytest.raises(RuntimeError):
        assert_safe_destructive_db()
