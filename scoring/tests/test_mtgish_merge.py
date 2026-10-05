"""mtgish_merge: base snapshot wins; upstream fills only cards the base lacks."""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mtgish_merge import merge, read_lines  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "mtgish_upstream_2026-10-02.json"
CARDS = {c["Name"]: c for c in json.loads(FIX.read_text(encoding="utf-8"))["cards"]}


def test_base_entry_wins_and_missing_cards_are_added():
    base_antman = copy.deepcopy(CARDS["Ant-Man, Scott Lang"])
    base_antman["Rules"] = []  # stands in for the older base parse
    upstream = [CARDS["Ant-Man, Scott Lang"], CARDS["Overwrite the Multiverse"]]
    merged, added = merge([base_antman], upstream)
    assert added == 1
    assert [c["Name"] for c in merged] == ["Ant-Man, Scott Lang", "Overwrite the Multiverse"]
    assert merged[0]["Rules"] == []  # the base entry was kept, not replaced


def test_names_match_case_and_accent_insensitively():
    base = [dict(CARDS["Mabel, Bitter Recluse"], Name="MÁBEL, BITTER RECLUSE")]
    merged, added = merge(base, [CARDS["Mabel, Bitter Recluse"]])
    assert added == 0 and len(merged) == 1


def test_upstream_entries_without_a_name_are_skipped():
    faces = {"_OracleCard": "Transforming", "FrontFace": {}, "BackFace": {}}
    merged, added = merge([], [faces, CARDS["Fate Transfer"]])
    assert added == 1 and merged == [CARDS["Fate Transfer"]]


def test_read_lines_parses_one_card_per_line(tmp_path):
    p = tmp_path / "mtgish.lines.json"
    p.write_text("\n".join(json.dumps(c) for c in CARDS.values()) + "\n\n", encoding="utf-8")
    assert [c["Name"] for c in read_lines(p)] == list(CARDS)


def test_duplicate_upstream_names_are_added_once():
    merged, added = merge([], [CARDS["Fate Transfer"], CARDS["Fate Transfer"]])
    assert added == 1 and len(merged) == 1
