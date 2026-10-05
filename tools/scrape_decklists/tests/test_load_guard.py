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
    # The floor only catches junk: names that are not cards. A commander
    # alone, or a commander plus names that resolve to nothing, is junk.
    assert load_corpus.deck_rejection(["Card 0"], known) == "too_few_resolvable"
    assert load_corpus.deck_rejection(
        ["Card 0", "Mainboard", "Sideboard", "Creature"], known) == "too_few_resolvable"
    # Small but real decks are kept: "any number of copies" decks (Relentless
    # Rats, Rat Colony, ...) store very few distinct names. 23 such decks in
    # prod (2026-10-05) have under 15 distinct names; the smallest has 2.
    assert load_corpus.deck_rejection(["Card 0", "Card 1"], known) is None
    real_14 = [f"Card {i}" for i in range(14)]
    assert load_corpus.deck_rejection(real_14, known) is None
    # Field names plus a full real list are still rejected.
    assert load_corpus.deck_rejection(real_14 + ["commander_v2"], known) == "field_names"
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
        "card_names": [commander, "Mainboard", "Sideboard"],
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


def _seed_rows(db: Path, deck_id: str, commander: str, cards: list[str]) -> None:
    """Write rows the way the pre-fix loader did (INSERT OR IGNORE, no replace)."""
    con = sqlite3.connect(db)
    con.execute("INSERT OR REPLACE INTO decks VALUES (?, 'archidekt', ?)", (deck_id, commander))
    con.executemany("INSERT OR IGNORE INTO deck_cards VALUES (?, ?)",
                    [(deck_id, c) for c in cards])
    con.commit()
    con.close()


def _deck_ids(db: Path) -> set[str]:
    con = sqlite3.connect(db)
    ids = {r[0] for r in con.execute("SELECT deck_id FROM decks")}
    con.close()
    return ids


def test_reloading_shell_records_purges_stored_field_name_rows(tmp_path, capsys):
    """Production state: shells already stored, their shell lines still in the JSONL.

    Reloading must remove the field-name rows. A deck left with no cards is
    removed; a mixed deck keeps its real cards; a good deck is untouched.
    """
    preview = json.loads((FIX / "edhrec_deckpreview_27071260.json").read_text(encoding="utf-8"))
    _source, _native_id, commander, names = runner._parse_edhrec_deckpreview(preview)
    scores = tmp_path / "scores.sqlite"
    _scores(scores, names)

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    out = tmp_path / "out"
    field = ["cards", "commander", "commander_v2"]
    shell_line = {"kind": "deck", "source": "archidekt", "commander": commander,
                  "card_names": field}
    good_line = {"kind": "deck", "source": "archidekt", "commander": commander,
                 "card_names": names}
    # pure: only a shell line ever. mixed: a good line and a shell line.
    # good: only a good line.
    _write_jsonl(corpus / "archidekt-refresh.jsonl", [
        shell_line | {"deck_id": "archidekt:pure"},
        good_line | {"deck_id": "archidekt:mixed"},
        shell_line | {"deck_id": "archidekt:mixed"},
        good_line | {"deck_id": "archidekt:good"},
    ])
    load_corpus.load(corpus, out, scores_db=scores)  # creates the schema
    db = out / "decks.sqlite"
    _seed_rows(db, "archidekt:pure", commander, field)
    _seed_rows(db, "archidekt:mixed", commander, field + names)
    capsys.readouterr()

    stats = load_corpus.load(corpus, out, scores_db=scores)

    assert _cards(db, "archidekt:pure") == []
    assert "archidekt:pure" not in _deck_ids(db)
    assert _cards(db, "archidekt:mixed") == sorted(names)
    assert _cards(db, "archidekt:good") == sorted(names)
    # The mixed deck's good line comes first, and its replace already drops
    # the seeded field-name rows; the purge counts only the pure shell's 3.
    assert stats["purged_shell_decks"] == 1
    assert stats["purged_field_name_rows"] == 3
    assert "purged shells: 1 decks, 3 field-name rows" in capsys.readouterr().out


def test_shell_record_never_removes_real_cards(tmp_path):
    """A shell line after a good line removes nothing but field-name rows."""
    preview = json.loads((FIX / "edhrec_deckpreview_27071260.json").read_text(encoding="utf-8"))
    _source, _native_id, commander, names = runner._parse_edhrec_deckpreview(preview)
    scores = tmp_path / "scores.sqlite"
    _scores(scores, names)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    _write_jsonl(corpus / "a.jsonl", [
        {"kind": "deck", "deck_id": "archidekt:1", "source": "archidekt",
         "commander": commander, "card_names": names},
        {"kind": "deck", "deck_id": "archidekt:1", "source": "archidekt",
         "commander": commander, "card_names": {"cards": {}, "commander": [], "commander_v2": []}},
        {"kind": "deck", "deck_id": "archidekt:1", "source": "archidekt",
         "commander": commander, "card_names": [commander, "Mainboard"]},
    ])
    load_corpus.load(corpus, tmp_path / "out", scores_db=scores)
    db = tmp_path / "out" / "decks.sqlite"
    assert _cards(db, "archidekt:1") == sorted(names)
    assert "archidekt:1" in _deck_ids(db)
