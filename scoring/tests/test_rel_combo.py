import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from relationships.combo import load_catalog_combos  # noqa: E402


def test_load_catalog_maps_names_to_ids(tmp_path):
    cat = {"combos": [
        {"id": "X-1", "pieces": ["Card A", "Card B"], "result": "Infinite mana",
         "steps": "do it", "source_url": "http://x"},
        {"id": "X-2", "pieces": ["Card A", "Missing Card"], "result": "n/a",
         "steps": "", "source_url": ""},
    ]}
    f = tmp_path / "combo_catalog.json"
    f.write_text(json.dumps(cat), encoding="utf-8")
    name_to_id = {"card a": "id-a", "card b": "id-b"}

    combos = load_catalog_combos([str(f)], name_to_id)
    assert len(combos) == 1                      # X-2 dropped (Missing Card absent)
    c = combos[0]
    assert c["combo_id"] == "X-1"
    assert sorted(c["member_ids"]) == ["id-a", "id-b"]
    assert c["result"] == "Infinite mana"
