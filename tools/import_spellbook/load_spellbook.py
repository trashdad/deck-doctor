"""SP7 load — data/spellbook_raw.jsonl -> data/spellbook.sqlite.

SCAFFOLD — implement per docs/superpowers/plans/2026-06-10-sp6-sp11-roadmap.md §7.2.
stdlib-only. Drop + recreate both tables on every run (idempotent rebuild).

Schema (binding):
    CREATE TABLE combos (
        combo_id    TEXT PRIMARY KEY,
        identity    TEXT,
        popularity  INTEGER,
        bracket_tag TEXT,
        description TEXT,
        mana_needed TEXT,
        easy_prereq TEXT,
        notable_prereq TEXT,
        produces    TEXT NOT NULL,     -- JSON array of feature names
        card_count  INTEGER NOT NULL
    );
    CREATE TABLE combo_cards (
        combo_id  TEXT NOT NULL,
        card_name TEXT NOT NULL,       -- exact spellbook name; Store resolves at load
        quantity  INTEGER NOT NULL DEFAULT 1,
        must_be_commander INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (combo_id, card_name)
    );
    CREATE INDEX idx_combo_cards_name ON combo_cards(card_name);

Keep a variant iff: status == "OK" AND legalities["commander"] is True AND not spoiler
AND 2 <= len(uses) <= 6. produces = [p["feature"]["name"] for p in variant["produces"]].
Print a summary: variants read / kept / skipped.

CLI: python tools/import_spellbook/load_spellbook.py \
       [--raw data/spellbook_raw.jsonl] [--out data/spellbook.sqlite]
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError("SP7 pending — roadmap §7.2")


if __name__ == "__main__":
    main()
