import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_cooccurrence import build  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "decklists" / "sample.jsonl"


def _seed_scores(db):
    """Minimal scores.sqlite: cards + a card_relationships row (structural synergy)."""
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE cards (id TEXT PRIMARY KEY, name TEXT)")
    names = ["Sol Ring", "Arcane Signet", "Command Tower", "Lightning Bolt",
             "Counterspell", "Doubling Season", "Goblin Chieftain", "Evolution Sage",
             "Swords to Plowshares", "Cultivate", "Atraxa, Praetors' Voice",
             "Krenko, Mob Boss", "Tymna the Weaver"]
    for n in names:
        con.execute("INSERT INTO cards VALUES (?,?)", (n.lower().replace(" ", "_").replace(",", "").replace("'", ""), n))
    con.execute("""CREATE TABLE card_relationships (
        a TEXT, b TEXT, similarity REAL, synergy_ab REAL, synergy_ba REAL,
        anti_synergy REAL, combo INT, combo_id TEXT, candidate INT, PRIMARY KEY (a,b))""")
    sr = "sol_ring"; asig = "arcane_signet"
    a, b = sorted([sr, asig])
    con.execute("INSERT INTO card_relationships VALUES (?,?,?,?,?,?,?,?,?)",
                (a, b, 0.1, 0.2, 0.2, 0.0, 0, None, 0))
    con.commit(); con.close()


def test_build_writes_cooccurrence_and_refuses(tmp_path):
    scores = str(tmp_path / "scores.sqlite")
    _seed_scores(scores)

    stats = build(scores_db=scores, decks_source=str(SAMPLE),
                  edhrec_source=str(SAMPLE), min_support=2, from_jsonl=True)

    con = sqlite3.connect(scores)
    a, b = sorted(["sol_ring", "arcane_signet"])
    row = con.execute("SELECT co_count, lift FROM card_cooccurrence WHERE a=? AND b=?",
                      (a, b)).fetchone()
    assert row is not None and row[0] >= 2

    rel = con.execute("SELECT structural_synergy_ab, synergy_ab FROM card_relationships "
                      "WHERE a=? AND b=?", (a, b)).fetchone()
    assert rel is not None
    assert abs(rel[0] - 0.2) < 1e-9
    assert rel[1] >= rel[0]
    con.close()
    assert stats["pairs"] >= 1
