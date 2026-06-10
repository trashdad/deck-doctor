"""Card + score store.

Loads card metadata (sample JSON now, simmander DB later) into memory for O(1)
lookups and opens the generated SQLite synergy store read-only. All public
methods are pure lookups — no scoring happens at request time.
"""

from __future__ import annotations

import json
import math
import sqlite3
from functools import lru_cache
from pathlib import Path

# Complement pairs: (producer_tag, consumer_tag).
# If card A has producer_tag and card B has consumer_tag, they synergize.
# Scored bidirectionally — if the target has the consumer, find producers.
_COMPLEMENT_PAIRS: list[tuple[str, str]] = [
    # Token production → token payoffs
    ("e:create_token", "t:etb"),
    ("e:create_token", "t:token_created"),
    ("e:create_token", "t:creature_dies"),
    ("e:create_token", "t:sacrifice"),
    ("e:create_token", "t:attacks"),
    ("e:populate",     "t:etb"),
    ("e:populate",     "t:token_created"),
    # Counter production → counter payoffs
    ("e:add_counter",  "t:counter_placed"),
    ("e:proliferate",  "t:counter_placed"),
    ("c:plus1",        "e:proliferate"),
    ("c:energy",       "e:proliferate"),
    ("c:poison",       "e:proliferate"),
    # Death / graveyard
    ("e:destroy",      "t:creature_dies"),
    ("e:exile",        "t:exiled"),
    ("e:sacrifice",    "t:creature_dies"),
    ("e:sacrifice",    "t:sacrifice"),
    ("e:mill",         "t:enters_graveyard"),
    ("e:discard",      "t:enters_graveyard"),
    ("e:discard",      "t:discard"),
    # Graveyard recursion
    ("e:mill",         "e:reanimate"),
    ("e:discard",      "e:reanimate"),
    ("e:reanimate",    "t:etb"),
    # Draw
    ("e:draw",         "t:draw"),
    # Land / ramp
    ("e:ramp",         "t:landfall"),
    ("perm:land",      "t:landfall"),
    # Artifact
    ("perm:artifact",  "t:etb"),
    # Bounce / blink
    ("e:bounce",       "t:etb"),
    # Combat
    ("e:pump",         "t:combat_damage"),
    # Lifegain
    ("e:gain_life",    "t:life_gained"),
    # Damage
    ("e:damage",       "t:damage_dealt"),
    # Copy / discover trigger cast
    ("e:copy",         "t:cast_spell"),
    ("e:discover",     "t:cast_spell"),
    # Tapping
    ("e:tap",          "t:tapped"),
]

from . import config


class Store:
    def __init__(self, cards_path: Path, scores_path: Path):
        self._cards: dict[str, dict] = {}
        self._ier: dict[str, float] = {}
        self._tags: dict[str, list[str]] = {}
        self.scores_path = scores_path
        self._load_cards(cards_path)
        self._load_score_enrichment(scores_path)
        self._load_semantics()

    def _load_cards(self, path: Path) -> None:
        if not path.exists():
            return
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        cards = data["data"] if isinstance(data, dict) and "data" in data else data
        for c in cards:
            self._cards[c["id"]] = c

    def _load_score_enrichment(self, path: Path) -> None:
        if not path.exists():
            return
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        for cid, ier, tags in conn.execute("SELECT id, ier, mechanic_tags FROM cards"):
            self._ier[cid] = ier
            self._tags[cid] = json.loads(tags or "[]")
        conn.close()

    # ---- card access -----------------------------------------------------
    def get(self, card_id: str) -> dict | None:
        card = self._cards.get(card_id)
        if card is None:
            return None
        enriched = dict(card)
        enriched["ier"] = self._ier.get(card_id)
        enriched["mechanic_tags"] = self._tags.get(card_id, [])
        return enriched

    def search(self, q: str = "", colors: str = "", type_q: str = "",
               max_cmc: float | None = None, limit: int = 60) -> list[dict]:
        q = q.lower().strip()
        color_set = {c.upper() for c in colors if c.strip()}
        type_q = type_q.lower().strip()
        out: list[dict] = []
        for cid, card in self._cards.items():
            if q and q not in card.get("name", "").lower():
                continue
            if type_q and type_q not in card.get("type_line", "").lower():
                continue
            if max_cmc is not None and (card.get("cmc") or 0) > max_cmc:
                continue
            if color_set and not color_set.issubset(set(card.get("color_identity") or [])):
                continue
            out.append(self.get(cid))  # type: ignore[arg-type]
            if len(out) >= limit:
                break
        return out

    def ier(self, card_id: str) -> float | None:
        return self._ier.get(card_id)

    # ---- synergy access (O(1) indexed reads) -----------------------------
    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(f"file:{self.scores_path}?mode=ro", uri=True)

    def pair(self, a: str, b: str) -> dict | None:
        if not self.scores_path.exists():
            return None
        key = tuple(sorted((a, b)))
        conn = self._conn()
        row = conn.execute(
            "SELECT card_a, card_b, css, der, lift FROM synergies "
            "WHERE card_a=? AND card_b=?",
            key,
        ).fetchone()
        conn.close()
        if not row:
            return None
        return {"card_a": row[0], "card_b": row[1], "css": row[2],
                "der": row[3], "lift": bool(row[4])}

    def relationship(self, a: str, b: str) -> dict | None:
        """Return the typed relationship edge from card_relationships, or None."""
        if not self.scores_path.exists():
            return None
        lo, hi = sorted([a, b])
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT similarity, synergy_ab, synergy_ba, anti_synergy, combo, combo_id "
                "FROM card_relationships WHERE a=? AND b=?",
                (lo, hi),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        finally:
            conn.close()
        if row is None:
            return None
        sim, ab, ba, anti, combo, combo_id = row
        # Orient synergy to the caller's (a, b) order
        syn_ab, syn_ba = (ab, ba) if a == lo else (ba, ab)
        return {
            "similarity": sim,
            "synergy_ab": syn_ab,
            "synergy_ba": syn_ba,
            "anti_synergy": anti,
            "combo": bool(combo),
            "combo_id": combo_id,
        }

    def cooccurrence(self, a: str, b: str) -> dict | None:
        """Co-occurrence block from card_cooccurrence, or None."""
        if not self.scores_path.exists():
            return None
        lo, hi = sorted([a, b])
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT co_count, lift, jaccard, support FROM card_cooccurrence "
                "WHERE a=? AND b=?", (lo, hi)).fetchone()
        except sqlite3.OperationalError:
            return None
        finally:
            conn.close()
        if row is None:
            return None
        return {"co_count": row[0], "lift": row[1], "jaccard": row[2], "support": row[3]}

    def deck_engines(self, ids: list[str]) -> dict:
        """Return engines and combos from the engines table that are fully in ids."""
        idset = set(ids)
        engines: list[dict] = []
        combos: list[dict] = []
        if not self.scores_path.exists():
            return {"engines": [], "combos": []}
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT engine_id, members, kind, asserted_combo, candidate FROM engines"
            ).fetchall()
        except sqlite3.OperationalError:
            return {"engines": [], "combos": []}
        finally:
            conn.close()
        import json as _json
        for engine_id, members_json, kind, asserted, candidate in rows:
            members = _json.loads(members_json)
            if set(members) <= idset:
                entry = {
                    "engine_id": engine_id,
                    "members": members,
                    "kind": kind,
                    "candidate": bool(candidate),
                }
                (combos if asserted else engines).append(entry)
        return {"engines": engines, "combos": combos}

    def neighbours(self, card_id: str, limit: int = 12) -> list[dict]:
        if not self.scores_path.exists():
            return []
        conn = self._conn()
        rows = conn.execute(
            "SELECT card_a, card_b, css, der, lift FROM synergies "
            "WHERE card_a=? OR card_b=? ORDER BY der DESC LIMIT ?",
            (card_id, card_id, limit),
        ).fetchall()
        conn.close()
        return [{"card_a": r[0], "card_b": r[1], "css": r[2],
                 "der": r[3], "lift": bool(r[4])} for r in rows]

    # ---- semantic tag access -----------------------------------------------
    def _load_semantics(self) -> None:
        """Load per-ability and flat semantic tags from the SQLite store."""
        self._ability_tags: dict[str, list[list[str]]] = {}  # card_id -> [[tags per ability]]
        self._flat_tags_sem: dict[str, list[str]] = {}        # card_id -> flat union
        self._tag_inverted: dict[str, list[str]] = {}         # tag -> [card_ids]
        self._idf: dict[str, float] = {}                      # tag -> IDF weight
        if not self.scores_path.exists():
            return
        conn = sqlite3.connect(f"file:{self.scores_path}?mode=ro", uri=True)
        # ability tags
        rows = conn.execute("SELECT card_id, ability_idx, tags FROM card_ability_tags ORDER BY card_id, ability_idx").fetchall()
        for card_id, _, tags_json in rows:
            self._ability_tags.setdefault(card_id, []).append(json.loads(tags_json))
        # flat tags
        for card_id, tags_json in conn.execute("SELECT card_id, tags FROM card_flat_tags").fetchall():
            self._flat_tags_sem[card_id] = json.loads(tags_json)
        # inverted index
        for tag, ids_json in conn.execute("SELECT tag, card_ids FROM tag_inverted_index").fetchall():
            self._tag_inverted[tag] = json.loads(ids_json)
        conn.close()
        # IDF weights: log(N / df)
        N = max(len(self._flat_tags_sem), 1)
        for tag, ids in self._tag_inverted.items():
            self._idf[tag] = math.log(N / max(len(ids), 1))

    def card_semantics(self, card_id: str) -> dict:
        """Return {flat_tags, ability_tags} for a card."""
        return {
            "flat_tags": self._flat_tags_sem.get(card_id, []),
            "ability_tags": self._ability_tags.get(card_id, []),
        }

    def search_by_semantics_mixed(
        self,
        linked_tags: list[str],
        flat_tags: list[str],
        limit: int = 50,
    ) -> list[dict]:
        """
        linked_tags: must all co-appear on at least one ability line.
        flat_tags: must each appear anywhere on the card.
        Returns the intersection, sorted by IER.
        """
        # Start with the most restrictive set (linked), then filter
        if linked_tags:
            tag_set = set(linked_tags)
            linked_ids = set()
            for card_id, ability_list in self._ability_tags.items():
                for ability_tags in ability_list:
                    if tag_set.issubset(set(ability_tags)):
                        linked_ids.add(card_id)
                        break
        else:
            linked_ids = set(self._flat_tags_sem.keys())

        # Filter for flat tags
        if flat_tags:
            flat_sets = [set(self._tag_inverted.get(t, [])) for t in flat_tags]
            flat_ids = flat_sets[0]
            for s in flat_sets[1:]:
                flat_ids &= s
            candidate_ids = linked_ids & flat_ids
        else:
            candidate_ids = linked_ids

        out = []
        for cid in list(candidate_ids)[:limit * 2]:
            card = self.get(cid)
            if card:
                out.append(card)
        out.sort(key=lambda c: c.get("ier") or 0, reverse=True)
        return out[:limit]

    def search_by_semantics(
        self, tags: list[str], linked: bool = False, limit: int = 50
    ) -> list[dict]:
        """
        Find cards that have all of `tags`.

        linked=False: each tag can appear anywhere on the card (flat union).
        linked=True: all tags must co-appear on at least ONE ability line.
        """
        if not tags:
            return []

        if not linked:
            # intersect per-tag candidate sets
            candidate_sets = [
                set(self._tag_inverted.get(t, [])) for t in tags
            ]
            ids = candidate_sets[0]
            for s in candidate_sets[1:]:
                ids &= s
        else:
            # find cards where at least one ability contains ALL requested tags
            tag_set = set(tags)
            ids = set()
            for card_id, ability_list in self._ability_tags.items():
                for ability_tags in ability_list:
                    if tag_set.issubset(set(ability_tags)):
                        ids.add(card_id)
                        break

        out = []
        for cid in list(ids)[:limit]:
            card = self.get(cid)
            if card:
                out.append(card)
        # Sort by IER descending
        out.sort(key=lambda c: c.get("ier") or 0, reverse=True)
        return out

    def similar_cards(self, card_id: str, limit: int = 20) -> list[dict]:
        """TF-IDF cosine similarity on flat semantic tags."""
        target_tags = set(self._flat_tags_sem.get(card_id, []))
        if not target_tags:
            return []
        target_vec = {t: self._idf.get(t, 0.0) for t in target_tags}
        target_norm = math.sqrt(sum(v * v for v in target_vec.values()))
        if target_norm == 0:
            return []
        candidates: set[str] = set()
        for t in target_tags:
            candidates.update(self._tag_inverted.get(t, []))
        candidates.discard(card_id)
        scores: list[tuple[float, str]] = []
        for cid in candidates:
            cand_tags = set(self._flat_tags_sem.get(cid, []))
            shared = target_tags & cand_tags
            dot = sum(target_vec[t] * self._idf.get(t, 0.0) for t in shared)
            cand_norm = math.sqrt(sum(self._idf.get(t, 0.0) ** 2 for t in cand_tags))
            if cand_norm == 0:
                continue
            scores.append((dot / (target_norm * cand_norm), cid))
        scores.sort(reverse=True)
        out: list[dict] = []
        for _, cid in scores[:limit * 2]:
            card = self.get(cid)
            if card:
                out.append(card)
            if len(out) >= limit:
                break
        return out

    def combo_cards(self, card_id: str, limit: int = 20) -> list[dict]:
        """Semantic complement score: find cards whose tags pair with this card's tags."""
        target_tags = set(self._flat_tags_sem.get(card_id, []))
        if not target_tags:
            return []
        scores: dict[str, float] = {}
        for prod_tag, cons_tag in _COMPLEMENT_PAIRS:
            weight = self._idf.get(prod_tag, 0.0) + self._idf.get(cons_tag, 0.0)
            if prod_tag in target_tags:
                for cid in self._tag_inverted.get(cons_tag, []):
                    if cid != card_id:
                        scores[cid] = scores.get(cid, 0.0) + weight
            if cons_tag in target_tags:
                for cid in self._tag_inverted.get(prod_tag, []):
                    if cid != card_id:
                        scores[cid] = scores.get(cid, 0.0) + weight
        top = sorted(scores.items(), key=lambda x: -x[1])
        out: list[dict] = []
        for cid, _ in top:
            card = self.get(cid)
            if card:
                out.append(card)
            if len(out) >= limit:
                break
        return out

    def oracle_search(self, pattern: str, limit: int = 50) -> list[dict]:
        """Full-text substring search across oracle_text, case-insensitive."""
        pat = pattern.lower()
        out: list[dict] = []
        for cid, card in self._cards.items():
            if pat in (card.get("oracle_text") or "").lower():
                out.append(self.get(cid))  # type: ignore[arg-type]
                if len(out) >= limit:
                    break
        return out

    def synergies_among(self, ids: list[str], limit: int = 20) -> list[dict]:
        """Top synergy edges whose both endpoints are in the deck."""
        idset = set(ids)
        edges: list[dict] = []
        for cid in ids:
            for edge in self.neighbours(cid, limit=50):
                other = edge["card_b"] if edge["card_a"] == cid else edge["card_a"]
                if other in idset:
                    edges.append(edge)
        # dedupe by sorted pair
        seen = set()
        uniq = []
        for e in sorted(edges, key=lambda x: x["der"], reverse=True):
            k = tuple(sorted((e["card_a"], e["card_b"])))
            if k in seen:
                continue
            seen.add(k)
            uniq.append(e)
        return uniq[:limit]


@lru_cache(maxsize=1)
def get_store() -> Store:
    return Store(config.CARDS_PATH, config.SCORES_PATH)
