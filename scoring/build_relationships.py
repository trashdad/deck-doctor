"""Build the relationship layer: resources -> measures + engines + combos -> tables.

Reads SP2 card_fingerprints from data/scores.sqlite, writes card_relationships and
engines tables. Leaves synergies / CSS / DER untouched (augment, not replace).

Bounded-scale design
--------------------
1. Load fingerprints, resources, vectors, flat tags, name_to_id from DB.
2. Compute candidate_pairs() via the resource-flow index (producer x consumer —
   much smaller than all-pairs O(N^2)).
3. For each candidate pair compute synergy + anti_synergy (fast set ops).
4. Top-K trim: keep a pair if it is in the top-30 synergy pairs for EITHER card,
   OR it is a catalog combo pair, OR its anti_synergy > 0. This bounds the
   persisted table to roughly <=60*N rows instead of O(N^2).
5. Compute similarity (cosine over fingerprint vectors) ONLY for the kept pairs.
6. Combo pairs from load_catalog_combos -> set combo=1, combo_id; always kept.
7. Bounded engine mining: seed kept pairs sorted by max(synergy) desc, cap at
   max_seeds=3000, max_per_seed=20. Also store each catalog combo as an engine row
   with asserted_combo=1. Mark asserted_combo=1 on mined engines matching a catalog.
8. Write card_relationships (PK (a,b), indexes on a/b synergy) and engines tables.
   Return {"pairs": #persisted, "engines": #mined, "asserted_combos": #combos}.

Usage:
    python scoring/build_relationships.py --db data/scores.sqlite \\
        --catalog C:/simmander/simmander/data/combo_catalog.json \\
        --catalog C:/simmander/simmander/data/known_combos.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fingerprints.schema import AbilityRecord          # noqa: E402
from fingerprints.derive import fingerprint_to_vector  # noqa: E402
from relationships.resources import card_resources     # noqa: E402
from relationships.graph import candidate_pairs        # noqa: E402
from relationships.measures import similarity, synergy, anti_synergy  # noqa: E402
from relationships.engines import mine_engines         # noqa: E402
from relationships.combo import load_catalog_combos    # noqa: E402

_TOP_K = 30          # max synergy-ranked pairs retained per card
_MAX_SEEDS = 3000    # engine-mining seed cap
_MAX_PER_SEED = 20   # engine-mining frontier cap per seed


def _load_fingerprints(con) -> dict:
    """card_id -> list[AbilityRecord], ordered by ability_idx."""
    out: dict = {}
    for cid, record in con.execute(
        "SELECT card_id, record FROM card_fingerprints ORDER BY card_id, ability_idx"
    ):
        out.setdefault(cid, []).append(AbilityRecord.from_dict(json.loads(record)))
    return out


def _load_flat_tags(con) -> dict:
    """card_id -> set[str]; empty dict if table absent."""
    out: dict = {}
    try:
        for cid, tags in con.execute("SELECT card_id, tags FROM card_flat_tags"):
            out[cid] = set(json.loads(tags))
    except sqlite3.OperationalError:
        pass
    return out


def _top_k_keep(
    pair_scores: list[tuple],   # [(a, b, ab, ba), ...]
    k: int,
) -> set[tuple]:
    """Return the set of (a,b) pairs that are top-k by max(ab,ba) for either card.

    Buckets each pair under BOTH its cards, sorts each bucket by max(ab,ba)
    descending, takes the first k, then unions all kept pairs.
    """
    # bucket: card_id -> list of (max_syn, (a,b))
    buckets: dict[str, list] = {}
    for a, b, ab, ba in pair_scores:
        score = max(ab, ba)
        buckets.setdefault(a, []).append((score, (a, b)))
        buckets.setdefault(b, []).append((score, (a, b)))

    kept: set[tuple] = set()
    for card_pairs in buckets.values():
        card_pairs.sort(key=lambda x: x[0], reverse=True)
        for _, pair in card_pairs[:k]:
            kept.add(pair)
    return kept


def build(db_path: str, catalog_paths: list[str] | None = None, kmax: int = 5) -> dict:
    """Orchestrate relationship measurement and write tables to db_path.

    Returns
    -------
    {"pairs": int, "engines": int, "asserted_combos": int}
    """
    con = sqlite3.connect(db_path)

    # ── 1. Load inputs ────────────────────────────────────────────────────────
    fps = _load_fingerprints(con)
    flat = _load_flat_tags(con)
    name_to_id = {name: cid for cid, name in con.execute("SELECT id, name FROM cards")}

    resources = {cid: card_resources(recs) for cid, recs in fps.items()}
    # Vectors computed lazily (only for kept pairs) — build lookup on demand
    _vec_cache: dict = {}

    def _vec(cid: str) -> dict:
        if cid not in _vec_cache:
            _vec_cache[cid] = fingerprint_to_vector(fps[cid]) if cid in fps else {}
        return _vec_cache[cid]

    # ── 2. Catalog combos ─────────────────────────────────────────────────────
    combos = load_catalog_combos(catalog_paths or [], name_to_id)
    combo_pair_id: dict[tuple, str] = {}
    for c in combos:
        ids = c["member_ids"]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                combo_pair_id[tuple(sorted((ids[i], ids[j])))] = c["combo_id"]

    # ── 3. Candidate pairs + synergy/anti_synergy ─────────────────────────────
    raw_pairs = candidate_pairs(resources) | set(combo_pair_id)

    pair_scores: list[tuple] = []  # (a, b, ab, ba)
    pair_anti: dict[tuple, float] = {}
    for pair in raw_pairs:
        a, b = pair
        if a not in resources or b not in resources:
            continue
        ab, ba = synergy(resources[a], resources[b])
        anti = anti_synergy(flat.get(a, set()), flat.get(b, set()))
        pair_scores.append((a, b, ab, ba))
        pair_anti[pair] = anti

    # ── 4. Top-K trim ─────────────────────────────────────────────────────────
    kept = _top_k_keep(pair_scores, _TOP_K)
    # Always keep combo pairs and pairs with nonzero anti_synergy
    for pair in set(combo_pair_id):
        kept.add(pair)
    for pair, anti in pair_anti.items():
        if anti > 0.0:
            kept.add(pair)

    # Build a fast lookup from pair_scores
    scores_map: dict[tuple, tuple] = {(a, b): (ab, ba) for a, b, ab, ba in pair_scores}

    # ── 5. Compute similarity only for kept pairs ─────────────────────────────
    rows: list[tuple] = []
    for pair in sorted(kept):          # sorted for determinism
        a, b = pair
        if a not in resources or b not in resources:
            continue
        ab, ba = scores_map.get(pair, (0.0, 0.0))
        sim = similarity(_vec(a), _vec(b))
        anti = pair_anti.get(pair, 0.0)
        cid = combo_pair_id.get(pair)
        rows.append((a, b, sim, ab, ba, anti, 1 if cid else 0, cid, 0))

    # ── 6. Bounded engine mining ──────────────────────────────────────────────
    # Seed kept pairs sorted by max(synergy) desc, capped to _MAX_SEEDS
    seeds_sorted = sorted(
        kept,
        key=lambda p: max(scores_map.get(p, (0.0, 0.0))),
        reverse=True,
    )
    engines = mine_engines(
        resources,
        kmax=kmax,
        max_per_seed=_MAX_PER_SEED,
        seeds=seeds_sorted,
        max_seeds=_MAX_SEEDS,
    )
    asserted_member_sets = {frozenset(c["member_ids"]) for c in combos}

    # ── 7. Write tables ───────────────────────────────────────────────────────
    con.executescript("""
        DROP TABLE IF EXISTS card_relationships;
        CREATE TABLE card_relationships (
            a TEXT, b TEXT, similarity REAL, synergy_ab REAL, synergy_ba REAL,
            anti_synergy REAL, combo INT, combo_id TEXT, candidate INT,
            PRIMARY KEY (a, b));
        CREATE INDEX idx_rel_a ON card_relationships(a, synergy_ab DESC);
        CREATE INDEX idx_rel_b ON card_relationships(b, synergy_ba DESC);
        DROP TABLE IF EXISTS engines;
        CREATE TABLE engines (
            engine_id TEXT PRIMARY KEY, members TEXT, kind TEXT,
            resources TEXT, score REAL, asserted_combo INT, candidate INT);
    """)
    con.executemany(
        "INSERT OR REPLACE INTO card_relationships VALUES (?,?,?,?,?,?,?,?,?)",
        rows,
    )

    # Asserted catalog combos stored as engine rows (asserted_combo=1)
    eng_rows: list[tuple] = []
    for c in combos:
        eng_rows.append((
            c["combo_id"],
            json.dumps(sorted(c["member_ids"])),
            "combo",
            json.dumps([]),
            1.0,
            1,
            0,
        ))

    # Mined engines — sorted by member tuple for determinism
    mined_sorted = sorted(engines, key=lambda e: tuple(sorted(e["members"])))
    for i, e in enumerate(mined_sorted):
        members = sorted(e["members"])
        eng_rows.append((
            f"eng-{i}",
            json.dumps(members),
            e["kind"],
            json.dumps([]),
            float(len(members)),
            1 if frozenset(members) in asserted_member_sets else 0,
            1 if e["candidate"] else 0,
        ))

    con.executemany("INSERT OR REPLACE INTO engines VALUES (?,?,?,?,?,?,?)", eng_rows)
    con.commit()
    con.close()

    return {
        "pairs": len(rows),
        "engines": len(engines),
        "asserted_combos": len(combos),
    }


def main() -> None:
    p = argparse.ArgumentParser(
        description="Build card_relationships + engines tables from SP2 fingerprints."
    )
    p.add_argument("--db", default="data/scores.sqlite")
    p.add_argument("--catalog", action="append", default=[])
    p.add_argument("--kmax", type=int, default=5)
    a = p.parse_args()
    stats = build(a.db, catalog_paths=a.catalog, kmax=a.kmax)
    print(
        f"relationships: {stats['pairs']:,} pairs  |  "
        f"engines: {stats['engines']:,}  |  "
        f"asserted combos: {stats['asserted_combos']:,}"
    )


if __name__ == "__main__":
    main()
