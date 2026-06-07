import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_fingerprints import build  # noqa: E402


def test_build_end_to_end(tmp_path):
    mtgish = [{
        "Name": "Test Drawer",
        "Rules": [{"_Rule": "TriggerA", "args": [
            {"_Trigger": "WhenAPermanentEntersTheBattlefield",
             "args": {"_Permanents": "SinglePermanent", "args": {"_Permanent": "ThisPermanent"}}},
            {"_Actions": "ActionList", "args": [{"_Action": "DrawACard"}]}]}],
    }]
    cards = [{"id": "id-1", "name": "Test Drawer"}]
    mp = tmp_path / "mtgish.json"; mp.write_text(json.dumps(mtgish), encoding="utf-8")
    cp = tmp_path / "cards.json"; cp.write_text(json.dumps(cards), encoding="utf-8")
    db = tmp_path / "scores.sqlite"

    stats = build(str(mp), str(cp), str(db), outliers_dir=str(tmp_path / "none"))

    assert stats["matched"] == 1
    con = sqlite3.connect(db)
    rec = con.execute("select record from card_fingerprints where card_id='id-1'").fetchone()
    assert rec is not None
    fp = json.loads(rec[0])
    assert fp["kind"] == "triggered"
    flat = con.execute("select tags from card_flat_tags where card_id='id-1'").fetchone()
    assert "e:draw" in json.loads(flat[0])
    con.close()
