"""Tags for operators the upstream MTGish schema restructured (i5jb/mtgish, 2026-10).

Upstream replaced PutACounterOfTypeOnPermanent & co. with PutCounters
(+ _PutCountersAction), ExilePermanent & co. with Exile (+ _Exilable), and the
RemoveACounter... / MoveACounter... family with RemoveCounters / MoveCounters.
The fixture holds real upstream entries; see its "source" field.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_semantics import ability_tag_lists  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "mtgish_upstream_2026-10-02.json"
CARDS = {c["Name"]: c for c in json.loads(FIX.read_text(encoding="utf-8"))["cards"]}


def _tags(name: str) -> set[str]:
    return {t for ability in ability_tag_lists(CARDS[name]["Rules"]) for t in ability}


def test_put_counters_tags_add_counter():
    assert "e:add_counter" in _tags("Ant-Man, Scott Lang")


def test_exile_tags_exile():
    assert "e:exile" in _tags("Overwrite the Multiverse")


def test_remove_counters_tags_remove_counter():
    assert "e:remove_counter" in _tags("Mabel, Bitter Recluse")


def test_move_counters_tags_both_counter_effects():
    assert {"e:add_counter", "e:remove_counter"} <= _tags("Fate Transfer")
