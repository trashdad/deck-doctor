"""Postgres access for the deckdoctor database (psycopg2, pooled).

The whole app — the read-only analytical tables and the read-write userdecks —
lives in one Postgres database (DATABASE_URL, default localhost/deckdoctor). The
analytical tables are loaded from the offline SQLite build artifacts by
scoring/load_to_postgres.py; userdecks is owned by app/decks.py.

A single ThreadedConnectionPool backs everything: FastAPI's sync endpoints run in
a threadpool, so connections are borrowed per call and returned. JSON-ish columns
are stored as TEXT (not jsonb) so existing json.loads(...) call-sites are unchanged.
"""

from __future__ import annotations

import contextlib
import threading

import psycopg2
from psycopg2 import pool as _pgpool

from . import config

_POOL: _pgpool.ThreadedConnectionPool | None = None
_LOCK = threading.Lock()


def init_pool(minconn: int = 1, maxconn: int = 16) -> _pgpool.ThreadedConnectionPool:
    global _POOL
    if _POOL is None:
        with _LOCK:
            if _POOL is None:
                _POOL = _pgpool.ThreadedConnectionPool(
                    minconn, maxconn, dsn=config.DATABASE_URL)
    return _POOL


def reset_pool() -> None:
    """Drop the pool (used by /admin/reload so the next request reconnects)."""
    global _POOL
    with _LOCK:
        if _POOL is not None:
            try:
                _POOL.closeall()
            except Exception:  # noqa: BLE001
                pass
            _POOL = None


@contextlib.contextmanager
def connection():
    pool = init_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


@contextlib.contextmanager
def cursor(commit: bool = False):
    """Borrow a cursor. Rolls back on error (so the connection is reusable),
    commits on success when commit=True."""
    with connection() as conn:
        cur = conn.cursor()
        try:
            yield cur
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def query(sql: str, params: tuple = ()) -> list[tuple]:
    """Run a read query, returning all rows. Missing table / DB error → [] so the
    Store degrades exactly like the old 'missing sqlite file → empty' behaviour."""
    try:
        with cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    except psycopg2.Error:
        return []


def query_one(sql: str, params: tuple = ()) -> tuple | None:
    rows = query(sql, params)
    return rows[0] if rows else None
