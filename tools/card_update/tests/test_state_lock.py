from __future__ import annotations

import json

import pytest

from card_update.lock import FileLock, LockTimeout
from card_update.state import State, StateError, load_state, save_state


# ── state ────────────────────────────────────────────────────────────────────

def test_missing_state_file_gives_fresh_state(tmp_path):
    st = load_state(tmp_path / "state.json")
    assert st == State()
    assert st.consecutive_failures == 0 and st.current_release_id is None


def test_state_round_trips_atomically(tmp_path):
    p = tmp_path / "sub" / "state.json"
    st = State(scryfall_updated_at="2026-11-26T10:06:21.722+00:00", mtgish_sha="a" * 40,
               cards_sha256="c" * 64, current_release_id="r1", consecutive_failures=2,
               last_success_utc="2026-11-25T02:31:00Z")
    save_state(p, st)
    assert load_state(p) == st
    assert not [x for x in p.parent.iterdir() if x.name.endswith(".tmp")]


def test_corrupt_state_fails_loudly_instead_of_resetting(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(StateError):
        load_state(p)


def test_wrongly_typed_state_field_fails(tmp_path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"consecutive_failures": "three"}), encoding="utf-8")
    with pytest.raises(StateError):
        load_state(p)


def test_unknown_state_keys_are_ignored_for_forward_compat(tmp_path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"mtgish_sha": "b" * 40, "future_field": 1}), encoding="utf-8")
    assert load_state(p).mtgish_sha == "b" * 40


# ── lock ─────────────────────────────────────────────────────────────────────

def test_lock_acquire_release_and_reacquire(tmp_path, clock):
    p = tmp_path / "data" / ".pipeline.lock"
    with FileLock(p, wait_s=0, clock=clock):
        assert p.exists()
    with FileLock(p, wait_s=0, clock=clock):
        pass


def test_held_lock_times_out_instead_of_skipping(tmp_path, clock):
    p = tmp_path / ".pipeline.lock"
    with FileLock(p, wait_s=0, clock=clock):
        with pytest.raises(LockTimeout) as ei:
            FileLock(p, wait_s=30, clock=clock, poll_s=5).acquire()
    assert str(p) in str(ei.value)
    assert sum(clock.sleeps) >= 30          # it really waited before failing


def test_lock_is_obtained_once_the_holder_releases(tmp_path, clock):
    p = tmp_path / ".pipeline.lock"
    holder = FileLock(p, wait_s=0, clock=clock)
    holder.acquire()
    original_sleep = clock.sleep

    def sleep_then_release(seconds):
        original_sleep(seconds)
        holder.release()
    clock.sleep = sleep_then_release
    waiter = FileLock(p, wait_s=60, clock=clock, poll_s=5)
    waiter.acquire()
    waiter.release()
