"""
Build semantic tag tables in scores.sqlite from MTGish typed card data.

Usage:
    python scoring/build_semantics.py \
        --mtgish C:/simmander/simmander/mtgish/data/cards.json \
        --cards  data/cards.json \
        --db     data/scores.sqlite

For each card that exists in both datasets we store:
  card_semantics(card_id TEXT, ability_idx INT, tags TEXT)
  -- one row per (card, ability), tags = JSON array of tag strings

Also writes a flat view:
  card_flat_tags(card_id TEXT, tags TEXT)
  -- one row per card, tags = union of all ability tags
"""

import argparse
import json
import sqlite3
import sys
import unicodedata
from pathlib import Path

# ── Add scoring dir to path so we can import tag_taxonomy ────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from tag_taxonomy import (
    TRIGGER_MAP, ACTION_MAP, COUNTER_MAP, KEYWORD_MAP,
    REPLACEMENT_MAP, PLAYER_MAP, PLAYERS_MAP, PERMANENT_CARDTYPE_MAP,
)

# ── Node extraction ───────────────────────────────────────────────────────────

def extract_nodes(node, result: list, depth: int = 0) -> None:
    """Flatten all typed operator nodes from an MTGish rule tree."""
    if depth > 20:
        return
    if isinstance(node, dict):
        # Check for typed node keys
        for typed_key in ("_Rule", "_Trigger", "_Action", "_Player", "_Players",
                          "_Permanent", "_Permanents", "_DamageSources", "_GameNumber"):
            if typed_key in node:
                result.append((typed_key, node[typed_key], node))

        # _CounterType with args for PT counters
        if "_CounterType" in node:
            result.append(("_CounterType", node["_CounterType"], node.get("args", [])))

        # _Permanents: "IsCardtype" — capture what card type the ability cares about
        if node.get("_Permanents") == "IsCardtype":
            result.append(("_IsCardtype", node.get("args", ""), node))

        # _Actions list (ActionList container)
        if "_Actions" in node:
            pass  # just recurse into args

        # Recurse into all values
        for val in node.values():
            if isinstance(val, (dict, list)):
                extract_nodes(val, result, depth + 1)

    elif isinstance(node, list):
        for item in node:
            extract_nodes(item, result, depth + 1)


def nodes_to_tags(nodes: list) -> list[str]:
    """Map raw nodes to semantic tag strings."""
    tags: set[str] = set()
    for entry in nodes:
        key, val, ctx = entry[0], entry[1], entry[2]

        if key == "_Rule":
            tags.update(KEYWORD_MAP.get(val, []))
            tags.update(REPLACEMENT_MAP.get(val, []))
            # TriggerA / TriggerAll are structural, not semantic by themselves
            if val == "Landfall":
                tags.add("t:landfall")
                tags.add("k:landfall")

        elif key == "_Trigger":
            tags.update(TRIGGER_MAP.get(val, []))

        elif key == "_Action":
            tags.update(ACTION_MAP.get(val, []))

        elif key == "_CounterType":
            ct_args = ctx  # ctx is node.get("args") here
            if val == "PTCounter":
                if isinstance(ct_args, list):
                    if ct_args == [1, 1]:
                        tags.add("c:plus1")
                    elif ct_args == [-1, -1]:
                        tags.add("c:minus1")
                    else:
                        tags.add("c:pt_counter")
                else:
                    tags.add("c:pt_counter")
            else:
                tags.update(COUNTER_MAP.get(val, []))

        elif key == "_Player":
            tags.update(PLAYER_MAP.get(val, []))

        elif key == "_Players":
            tags.update(PLAYERS_MAP.get(val, []))

        elif key == "_IsCardtype":
            tags.update(PERMANENT_CARDTYPE_MAP.get(str(val), []))

    return sorted(tags)


def ability_tag_lists(rules: list) -> list[list[str]]:
    """
    Return one tag-list per top-level rule in the card's Rules array.
    Each element corresponds to a single ability line.
    """
    result = []
    for rule in rules:
        nodes: list = []
        extract_nodes(rule, nodes)
        tags = nodes_to_tags(nodes)
        if tags:
            result.append(tags)
        else:
            result.append([])  # keep ability index aligned
    return result


# ── Name normalization for matching ──────────────────────────────────────────

def norm_name(name: str) -> str:
    """Lower-case, strip accents, collapse whitespace for fuzzy name matching."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_name.lower().strip()


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Build semantic tag tables.")
    parser.add_argument("--mtgish", default="C:/simmander/simmander/mtgish/data/cards.json")
    parser.add_argument("--cards",  default="data/cards.json")
    parser.add_argument("--db",     default="data/scores.sqlite")
    args = parser.parse_args()

    print("Loading MTGish cards ...")
    with open(args.mtgish, encoding="utf-8") as fh:
        mtgish_cards: list[dict] = json.load(fh)
    print(f"  {len(mtgish_cards):,} MTGish cards")

    print("Loading Scryfall cards ...")
    with open(args.cards, encoding="utf-8") as fh:
        raw = json.load(fh)
    sf_cards: list[dict] = raw["data"] if isinstance(raw, dict) and "data" in raw else raw
    print(f"  {len(sf_cards):,} Scryfall cards")

    # Build name -> Scryfall ID map
    sf_name_map: dict[str, str] = {}
    for c in sf_cards:
        sf_name_map[norm_name(c["name"])] = c["id"]

    print("Processing MTGish rules into tags ...")
    rows_ability: list[tuple] = []   # (card_id, ability_idx, tags_json)
    rows_flat: list[tuple] = []      # (card_id, tags_json)
    matched = 0
    unmatched = 0

    for mc in mtgish_cards:
        name = mc.get("Name", "")
        rules = mc.get("Rules", [])
        if not name or not rules:
            continue

        sf_id = sf_name_map.get(norm_name(name))
        if sf_id is None:
            unmatched += 1
            continue

        ability_lists = ability_tag_lists(rules)
        flat_tags: set[str] = set()

        for idx, tags in enumerate(ability_lists):
            rows_ability.append((sf_id, idx, json.dumps(tags)))
            flat_tags.update(tags)

        rows_flat.append((sf_id, json.dumps(sorted(flat_tags))))
        matched += 1

    print(f"  Matched {matched:,} cards  |  unmatched {unmatched:,}")

    # ── Write to SQLite ───────────────────────────────────────────────────────
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Writing to {db_path} ...")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    conn.executescript("""
        DROP TABLE IF EXISTS card_ability_tags;
        CREATE TABLE card_ability_tags (
            card_id    TEXT NOT NULL,
            ability_idx INTEGER NOT NULL,
            tags       TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (card_id, ability_idx)
        );

        DROP TABLE IF EXISTS card_flat_tags;
        CREATE TABLE card_flat_tags (
            card_id TEXT PRIMARY KEY,
            tags    TEXT NOT NULL DEFAULT '[]'
        );

        DROP INDEX IF EXISTS idx_flat_tags_card;
    """)

    conn.executemany(
        "INSERT OR REPLACE INTO card_ability_tags VALUES (?, ?, ?)",
        rows_ability,
    )
    conn.executemany(
        "INSERT OR REPLACE INTO card_flat_tags VALUES (?, ?)",
        rows_flat,
    )

    # Build inverted index: tag -> [card_ids] stored as JSON in a lookup table
    print("Building inverted index ...")
    from collections import defaultdict
    inverted: dict[str, set[str]] = defaultdict(set)
    for card_id, tags_json in rows_flat:
        for tag in json.loads(tags_json):
            inverted[tag].add(card_id)

    conn.execute("DROP TABLE IF EXISTS tag_inverted_index")
    conn.execute("""
        CREATE TABLE tag_inverted_index (
            tag      TEXT PRIMARY KEY,
            card_ids TEXT NOT NULL DEFAULT '[]'
        )
    """)
    conn.executemany(
        "INSERT INTO tag_inverted_index VALUES (?, ?)",
        [(tag, json.dumps(sorted(ids))) for tag, ids in inverted.items()],
    )

    conn.execute("CREATE INDEX IF NOT EXISTS idx_flat_tags_card ON card_flat_tags(card_id)")
    conn.commit()
    conn.close()

    print(f"Done.  {len(rows_ability):,} ability rows  |  {len(rows_flat):,} card rows  "
          f"|  {len(inverted):,} unique tags")


if __name__ == "__main__":
    main()
