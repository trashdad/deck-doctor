import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prep_cards import _keep  # noqa: E402


def _base(**over):
    c = {"lang": "en", "layout": "normal",
         "legalities": {"commander": "legal"},
         "set_type": "expansion", "border_color": "black"}
    c.update(over)
    return c


def test_keep_normal_commander_card():
    assert _keep(_base()) is True


def test_drop_acorn_stamp():
    assert _keep(_base(security_stamp="acorn")) is False


def test_drop_silver_border():
    assert _keep(_base(border_color="silver")) is False


def test_drop_funny_set():
    assert _keep(_base(set_type="funny")) is False


from prep_cards import select_prints  # noqa: E402


def _print(pid, oid, released, image=True):
    c = _base(id=pid, oracle_id=oid, released_at=released)
    if image:
        c["image_uris"] = {"normal": f"https://img/{pid}.jpg"}
    return c


def test_select_prefers_newest_print_without_pins():
    cards = [_print("old", "o1", "2020-01-01"), _print("new", "o1", "2026-06-26")]
    assert [c["id"] for c in select_prints(cards)] == ["new"]


def test_pinned_print_keeps_its_id_when_a_reprint_appears():
    # A Scryfall refresh adds a reprint; the card id users and tables already
    # reference must not change.
    cards = [_print("old", "o1", "2020-01-01"), _print("new", "o1", "2026-06-26"),
             _print("fresh", "o2", "2026-10-02")]
    got = {c["oracle_id"]: c["id"] for c in select_prints(cards, keep_ids={"old"})}
    assert got == {"o1": "old", "o2": "fresh"}


def test_pin_falls_back_to_newest_when_pinned_print_is_gone():
    cards = [_print("a", "o1", "2020-01-01"), _print("b", "o1", "2026-06-26")]
    assert [c["id"] for c in select_prints(cards, keep_ids={"removed"})] == ["b"]


def test_pinned_print_must_still_pass_the_filter():
    cards = [_print("old", "o1", "2020-01-01") | {"security_stamp": "acorn"},
             _print("new", "o1", "2026-06-26")]
    assert [c["id"] for c in select_prints(cards, keep_ids={"old"})] == ["new"]
