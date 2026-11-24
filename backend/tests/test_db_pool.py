"""Regression: psycopg2 closes returned connections beyond `minconn` idle ones, so a tiny floor
made concurrent requests open a new Postgres session per query (4 parallel /deck/recommend
calls took 35 s and opened ~880 sessions in a real-backend run, 2026-11-24)."""
import inspect
import threading
import time

from app import db


def test_default_pool_keeps_a_warm_floor():
    assert inspect.signature(db.init_pool).parameters["minconn"].default >= 4


def test_concurrent_queries_reuse_connections():
    db.reset_pool()
    pool = db.init_pool()
    seen = set()

    def work():
        for _ in range(20):
            with db.cursor() as cur:
                cur.execute("select pg_backend_pid()")
                seen.add(cur.fetchone()[0])

    threads = [threading.Thread(target=work) for _ in range(6)]
    t0 = time.time()
    [t.start() for t in threads]
    [t.join() for t in threads]
    # 6 workers can never need more than 6 sessions if returned connections are kept.
    assert len(seen) <= 8, f"{len(seen)} distinct sessions for 6 threads: pool is churning"
    assert time.time() - t0 < 10
    assert pool.minconn >= 4
