"""Loader guard: field-name shells and under-resolved decks are not stored."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

SCRAPER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRAPER))

import load_corpus  # noqa: E402
import runner  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"


def _scores(path: Path, names: list[str]) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE cards (id TEXT PRIMARY KEY, name TEXT)")
    con.executemany("INSERT INTO cards VALUES (?, ?)", [(str(i), n) for i, n in enumerate(names)])
    con.commit()
    con.close()


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(r) + "\n" for r in records),
        encoding="utf-8",
    )


def _cards(db: Path, deck_id: str) -> list[str]:
    con = sqlite3.connect(db)
    rows = [r[0] for r in con.execute(
        "SELECT card_name FROM deck_cards WHERE deck_id = ? ORDER BY card_name", (deck_id,))]
    con.close()
    return rows


def test_rejection_rules():
    known = {_norm for _norm in (
        load_corpus._norm(n) for n in ["Sol Ring", "Arcane Signet"] + [f"Card {i}" for i in range(20)]
    )}
    assert load_corpus.deck_rejection(
        ["cards", "commander", "commander_v2"], known) == "field_names"
    assert load_corpus.deck_rejection(
        {"cards": [], "commander": [], "commander_v2": []}, known) == "field_names"
    real_14 = [f"Card {i}" for i in range(14)]
    assert load_corpus.deck_rejection(real_14, known) == "too_few_resolvable"
    real_15 = [f"Card {i}" for i in range(15)]
    assert load_corpus.deck_rejection(real_15, known) is None
    # Field names plus a full real list are still rejected.
    assert load_corpus.deck_rejection(real_15 + ["commander_v2"], known) == "field_names"
    assert load_corpus.deck_rejection([], known) == "empty"


def test_loader_rejects_shell_and_short_deck_and_replaces_cards(tmp_path, capsys):
    preview = json.loads((FIX / "edhrec_deckpreview_27071260.json").read_text(encoding="utf-8"))
    parsed = runner._parse_edhrec_deckpreview(preview)
    assert parsed is not None
    _source, native_id, commander, names = parsed
    assert len(names) >= 15

    scores = tmp_path / "scores.sqlite"
    _scores(scores, names + [f"Extra {i}" for i in range(20)])

    good = {
        "kind": "deck", "deck_id": f"archidekt:{native_id}", "source": "archidekt",
        "commander": commander, "card_names": names,
    }
    shell = {
        "kind": "deck", "deck_id": "moxfield:shell", "source": "moxfield",
        "commander": "Krenko, Mob Boss",
        "card_names": ["cards", "commander", "commander_v2"],
    }
    short = {
        "kind": "deck", "deck_id": "archidekt:short", "source": "archidekt",
        "commander": "Krenko, Mob Boss",
        "card_names": names[:10],
    }
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    _write_jsonl(corpus / "batch.jsonl", [shell, short, good])

    stats = load_corpus.load(corpus, tmp_path / "out", scores_db=scores)
    err = capsys.readouterr().out
    assert "rejected decks: 2" in err
    assert "field_names=1" in err
    assert "too_few_resolvable=1" in err
    assert stats["rejected_decks"] == 2
    assert stats["rejected_field_names"] == 1
    assert stats["rejected_too_few_resolvable"] == 1
    assert stats["unique_decks"] == 1

    db = tmp_path / "out" / "decks.sqlite"
    assert _cards(db, f"archidekt:{native_id}") == sorted(names)
    assert _cards(db, "moxfield:shell") == []
    assert _cards(db, "archidekt:short") == []

    # A later shell record must not put field names onto the good deck,
    # and a later good record must replace a previously stored shell.
    _write_jsonl(corpus / "later.jsonl", [{
        "kind": "deck", "deck_id": f"archidekt:{native_id}", "source": "archidekt",
        "commander": commander, "card_names": ["cards", "commander", "commander_v2"],
    }])
    load_corpus.load(corpus, tmp_path / "out", scores_db=scores)
    assert _cards(db, f"archidekt:{native_id}") == sorted(names)

    corpus2 = tmp_path / "corpus2"
    corpus2.mkdir()
    out2 = tmp_path / "out2"
    # Rejected shell does not create rows. Seed the pre-fix shell, then a good record.
    _write_jsonl(corpus2 / "a.jsonl", [shell | {"deck_id": "archidekt:9", "source": "archidekt"}])
    load_corpus.load(corpus2, out2, scores_db=scores)
    # manually represent the pre-fix rows, then reload a good parse over them
    con = sqlite3.connect(out2 / "decks.sqlite")
    con.execute("INSERT INTO decks VALUES ('archidekt:9', 'archidekt', 'Krenko, Mob Boss')")
    con.executemany(
        "INSERT INTO deck_cards VALUES ('archidekt:9', ?)",
        [("cards",), ("commander",), ("commander_v2",)],
    )
    con.commit()
    con.close()
    _write_jsonl(corpus2 / "b.jsonl", [{
        "kind": "deck", "deck_id": "archidekt:9", "source": "archidekt",
        "commander": commander, "card_names": names,
    }])
    load_corpus.load(corpus2, out2, scores_db=scores)
    stored = _cards(out2 / "decks.sqlite", "archidekt:9")
    assert stored == sorted(names)
    assert not ({"cards", "commander", "commander_v2"} & set(stored))
