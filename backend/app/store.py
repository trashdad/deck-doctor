"""Card + score store.

Loads card metadata (sample JSON now, simmander DB later) into memory for O(1)
lookups and opens the generated SQLite synergy store read-only. All public
methods are pure lookups — no scoring happens at request time.
"""

from __future__ import annotations

import json
import math
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

from . import config, db


class Store:
    def __init__(self, cards_path: Path):
        self._cards: dict[str, dict] = {}
        self._ier: dict[str, float] = {}
        self._tags: dict[str, list[str]] = {}
        self.scores_loaded = False
        self._load_cards(cards_path)
        self._load_score_enrichment()
        self._load_semantics()
        self._load_name_index()
        self._load_edhrec()
        self._load_engines()
        self._load_staples()
        self._load_spellbook()
        self._load_commander_decks()
        self._load_land_meta(cards_path)

    def _load_cards(self, path: Path) -> None:
        if not path.exists():
            return
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        cards = data["data"] if isinstance(data, dict) and "data" in data else data
        for c in cards:
            self._cards[c["id"]] = c

    def _load_score_enrichment(self) -> None:
        rows = db.query("SELECT id, ier, mechanic_tags FROM cards")
        for cid, ier, tags in rows:
            self._ier[cid] = ier
            self._tags[cid] = json.loads(tags or "[]")
        self.scores_loaded = bool(rows)

    # ---- card access -----------------------------------------------------
    def get(self, card_id: str) -> dict | None:
        card = self._cards.get(card_id)
        if card is None:
            return None
        enriched = dict(card)
        enriched["ier"] = self._ier.get(card_id)
        enriched["mechanic_tags"] = self._tags.get(card_id, [])
        enriched["semantic_tags"] = self._flat_tags_sem.get(card_id, [])
        return enriched

    def search(self, q: str = "", colors: str = "", type_q: str = "",
               max_cmc: float | None = None, limit: int = 60,
               commander_id: str | None = None, oracle: str = "") -> list[dict]:
        """Filtered card search, ranked MOST-POPULAR first.

        Ranking: when a `commander_id` is given, by that commander's EDHREC
        inclusion rate (the cards its decks actually run), then global corpus
        deck-frequency; otherwise by global deck-frequency. So the empty-query
        default surfaces the most-played cards, contextualised to the commander.
        """
        q = q.lower().strip()
        oracle = oracle.lower().strip()
        color_set = {c.upper() for c in colors if c.strip()}
        type_q = type_q.lower().strip()
        matches: list[str] = []
        for cid, card in self._cards.items():
            if q and q not in card.get("name", "").lower():
                continue
            if oracle and oracle not in (card.get("oracle_text", "") or "").lower():
                continue
            if type_q and type_q not in card.get("type_line", "").lower():
                continue
            if max_cmc is not None and (card.get("cmc") or 0) > max_cmc:
                continue
            if color_set and not color_set.issubset(set(card.get("color_identity") or [])):
                continue
            matches.append(cid)

        edh = self.edhrec_for(commander_id) if commander_id else {}
        if edh:
            matches.sort(key=lambda cid: (
                -edh.get(cid, (0.0, 0.0))[1],          # commander inclusion rate
                -self._deck_freq.get(cid, 0),           # global popularity
                self._cards[cid].get("name", "")))
        else:
            matches.sort(key=lambda cid: (
                -self._deck_freq.get(cid, 0),
                self._cards[cid].get("name", "")))
        return [self.get(cid) for cid in matches[:limit]]  # type: ignore[misc]

    def ier(self, card_id: str) -> float | None:
        return self._ier.get(card_id)

    # ---- synergy access (O(1) indexed reads against Postgres) ------------
    def pair(self, a: str, b: str) -> dict | None:
        key = tuple(sorted((a, b)))
        row = db.query_one(
            "SELECT card_a, card_b, css, der, lift FROM synergies "
            "WHERE card_a=%s AND card_b=%s", key)
        if not row:
            return None
        return {"card_a": row[0], "card_b": row[1], "css": row[2],
                "der": row[3], "lift": bool(row[4])}

    def relationship(self, a: str, b: str) -> dict | None:
        """Return the typed relationship edge from card_relationships, or None."""
        lo, hi = sorted([a, b])
        row = db.query_one(
            "SELECT similarity, synergy_ab, synergy_ba, anti_synergy, combo, combo_id "
            "FROM card_relationships WHERE a=%s AND b=%s", (lo, hi))
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
        lo, hi = sorted([a, b])
        row = db.query_one(
            "SELECT co_count, lift, jaccard, support FROM card_cooccurrence "
            "WHERE a=%s AND b=%s", (lo, hi))
        if row is None:
            return None
        return {"co_count": row[0], "lift": row[1], "jaccard": row[2], "support": row[3]}

    def deck_engines(self, ids: list[str]) -> dict:
        """Return engines and combos (from the in-memory index) fully contained in ids."""
        idset = set(ids)
        engines: list[dict] = []
        combos: list[dict] = []
        seen: set[str] = set()
        for cid in idset:
            for idx in self._engines_by_member.get(cid, ()):
                eng = self._engines[idx]
                if eng["engine_id"] in seen:
                    continue
                if set(eng["members"]) <= idset:
                    seen.add(eng["engine_id"])
                    entry = {
                        "engine_id": eng["engine_id"],
                        "members": eng["members"],
                        "kind": eng["kind"],
                        "candidate": eng["candidate"],
                    }
                    (combos if eng["asserted"] else engines).append(entry)
        return {"engines": engines, "combos": combos}

    def neighbours(self, card_id: str, limit: int = 12) -> list[dict]:
        rows = db.query(
            "SELECT card_a, card_b, css, der, lift FROM synergies "
            "WHERE card_a=%s OR card_b=%s ORDER BY der DESC LIMIT %s",
            (card_id, card_id, limit))
        return [{"card_a": r[0], "card_b": r[1], "css": r[2],
                 "der": r[3], "lift": bool(r[4])} for r in rows]

    # ---- SP5/SP4 startup loads -------------------------------------------
    def _load_name_index(self) -> None:
        """name (lowercased; full + front face of `A // B`) -> card id."""
        self._name_to_id: dict[str, str] = {}
        for cid, card in self._cards.items():
            name = (card.get("name") or "").lower()
            if not name:
                continue
            self._name_to_id.setdefault(name, cid)
            if " // " in name:
                self._name_to_id.setdefault(name.split(" // ", 1)[0], cid)

    def _load_edhrec(self) -> None:
        """commander_id -> {card_id: (synergy, inclusion)}; empty when table absent."""
        self._edhrec: dict[str, dict[str, tuple[float, float]]] = {}
        rows = db.query(
            "SELECT commander, card_name, synergy, inclusion FROM edhrec_metrics")
        for commander, card_name, synergy, inclusion in rows:
            cmd_id = self._name_to_id.get((commander or "").lower())
            card_id = self._name_to_id.get((card_name or "").lower())
            if cmd_id is None or card_id is None:
                continue
            self._edhrec.setdefault(cmd_id, {})[card_id] = (
                synergy or 0.0, inclusion or 0.0)

    def _load_engines(self) -> None:
        """All engines rows in memory + inverted member -> engine indices."""
        self._engines: list[dict] = []
        self._engines_by_member: dict[str, list[int]] = {}
        rows = db.query(
            "SELECT engine_id, members, kind, asserted_combo, candidate, score FROM engines")
        for engine_id, members_json, kind, asserted, candidate, score in rows:
            members = json.loads(members_json)
            idx = len(self._engines)
            self._engines.append({
                "engine_id": engine_id, "members": members, "kind": kind,
                "asserted": bool(asserted), "candidate": bool(candidate),
                "score": score or 0.0,
            })
            for m in members:
                self._engines_by_member.setdefault(m, []).append(idx)

    def _load_staples(self) -> None:
        """Per-card deck-frequency proxy (max co_count over its pairs), sorted desc."""
        freq: dict[str, int] = {}
        for side in ("a", "b"):
            for cid, mx in db.query(
                    f"SELECT {side}, MAX(co_count) FROM card_cooccurrence GROUP BY {side}"):
                if mx and mx > freq.get(cid, 0):
                    freq[cid] = mx
        self._deck_freq = freq
        self._staples: list[tuple[str, int]] = sorted(
            freq.items(), key=lambda kv: (-kv[1], kv[0]))

    def edhrec_for(self, commander_id: str) -> dict[str, tuple[float, float]]:
        return self._edhrec.get(commander_id, {})

    # ---- commander popularity (corpus deck count) ------------------------
    def _load_commander_decks(self) -> None:
        """commander card_id -> number of corpus decks led by it (popularity proxy).

        corpus_decks carries one row per scraped deck with a `commander` NAME; we
        count rows per name and resolve each name to a card id via the name index.
        Absent/empty ⇒ all zero (the commander list still renders, just without a
        popularity signal). Partner/pair commanders are keyed on the single stored
        name in v1 — multi-commander attribution is a later refinement.
        """
        self._commander_decks: dict[str, int] = {}
        rows = db.query(
            "SELECT commander, COUNT(*) FROM corpus_decks "
            "WHERE commander IS NOT NULL AND commander != '' "
            "GROUP BY commander")
        for name, count in rows:
            cid = self._name_to_id.get((name or "").lower())
            if cid is not None:  # several names (e.g. `A // B`) may map to one id
                self._commander_decks[cid] = self._commander_decks.get(cid, 0) + count

    def commander_deck_count(self, card_id: str) -> int:
        return self._commander_decks.get(card_id, 0)

    # ---- SP12: land meta (prices + produced_mana) -------------------------
    def _load_land_meta(self, cards_path: Path) -> None:
        """Load backend/data/land_meta.json into memory.

        Maps card id -> {"name": str, "produced_mana": list[str], "usd": float|None}.
        Missing file ⇒ empty dict (engine degrades gracefully — lands are still
        recommended, just without price filtering).
        """
        self.land_meta: dict[str, dict] = {}
        # land_meta.json lives in backend/data/ (same dir as this package's parent)
        meta_path = Path(__file__).resolve().parents[1] / "data" / "land_meta.json"
        if not meta_path.exists():
            return
        with meta_path.open(encoding="utf-8") as fh:
            self.land_meta = json.load(fh)
        print(f"land_meta: {len(self.land_meta)} entries loaded")

    def commanders(self, q: str = "", colors: str = "", sort: str = "popularity",
                   limit: int = 0) -> list[dict]:
        """Legendary creatures + planeswalkers, enriched with `deck_count`.

        q = case-insensitive name substring; colors = WUBRG subset the commander's
        color identity must contain; sort = popularity (deck_count desc) | name |
        ier (efficiency desc). limit<=0 ⇒ no cap. Name is the stable tiebreak.
        """
        q = q.lower().strip()
        color_set = {c.upper() for c in colors if c.strip()}
        out: list[dict] = []
        for cid, card in self._cards.items():
            tl = (card.get("type_line") or "").lower()
            if "legendary" not in tl:
                continue
            if "creature" not in tl and "planeswalker" not in tl:
                continue
            if q and q not in (card.get("name") or "").lower():
                continue
            if color_set and not color_set.issubset(set(card.get("color_identity") or [])):
                continue
            enriched = self.get(cid)
            if not enriched:
                continue
            enriched["deck_count"] = self._commander_decks.get(cid, 0)
            out.append(enriched)
        if sort == "name":
            out.sort(key=lambda c: c.get("name", ""))
        elif sort == "ier":
            out.sort(key=lambda c: (-(c.get("ier") or 0.0), c.get("name", "")))
        else:  # popularity (default)
            out.sort(key=lambda c: (-c["deck_count"], c.get("name", "")))
        return out[:limit] if limit and limit > 0 else out

    # ---- SP7: Commander Spellbook combos (roadmap §7.3) -------------------
    def _load_spellbook(self) -> None:
        """Load the spellbook combos into memory; resolve card names to ids.

        Combos with any unresolvable member are skipped (counted + logged once).
        Empty tables ⇒ both structures stay empty (engine degrades, never breaks).
        """
        self._spellbook: list[dict] = []
        self._spellbook_by_member: dict[str, list[int]] = {}
        combos = db.query(
            "SELECT combo_id, identity, popularity, bracket_tag, description, "
            "mana_needed, produces FROM combos")
        members_by_combo: dict[str, list[str]] = {}
        for combo_id, card_name in db.query(
                "SELECT combo_id, card_name FROM combo_cards"):
            members_by_combo.setdefault(combo_id, []).append(card_name)

        skipped = 0
        for combo_id, identity, popularity, bracket_tag, description, mana_needed, produces in combos:
            names = members_by_combo.get(combo_id, [])
            member_ids = [self._name_to_id.get((n or "").lower()) for n in names]
            if not member_ids or any(m is None for m in member_ids):
                skipped += 1
                continue
            idx = len(self._spellbook)
            self._spellbook.append({
                "combo_id": combo_id,
                "members": member_ids,
                "identity": identity or "",
                "popularity": popularity,
                "bracket_tag": bracket_tag or "",
                "description": description or "",
                "produces": json.loads(produces or "[]"),
                "mana_needed": mana_needed or "",
            })
            for m in member_ids:
                self._spellbook_by_member.setdefault(m, []).append(idx)
        print(f"spellbook: {len(self._spellbook)} combos loaded, "
              f"{skipped} skipped (unresolved cards)")

    def spellbook_with(self, card_id: str) -> list[dict]:
        """Combos containing card_id, popularity DESC (None last)."""
        combos = [self._spellbook[i] for i in self._spellbook_by_member.get(card_id, ())]
        combos.sort(key=lambda c: (c["popularity"] is None, -(c["popularity"] or 0),
                                   c["combo_id"]))
        return combos

    def deck_spellbook(self, ids: list[str]) -> dict:
        """{"complete": [combo], "near": [{"combo":…, "missing": card_id}]}.

        Union of member-indexed combos; classify by missing-member count
        (0 ⇒ complete, 1 ⇒ near). Each list popularity DESC; near capped at 50.
        """
        idset = set(ids)
        seen: set[str] = set()
        complete: list[dict] = []
        near: list[tuple[dict, str]] = []
        for cid in idset:
            for i in self._spellbook_by_member.get(cid, ()):
                combo = self._spellbook[i]
                if combo["combo_id"] in seen:
                    continue
                seen.add(combo["combo_id"])
                missing = [m for m in combo["members"] if m not in idset]
                if not missing:
                    complete.append(combo)
                elif len(missing) == 1:
                    near.append((combo, missing[0]))

        def _pop(c: dict) -> tuple:
            return (c["popularity"] is None, -(c["popularity"] or 0), c["combo_id"])

        complete.sort(key=_pop)
        near.sort(key=lambda t: _pop(t[0]))
        return {
            "complete": complete,
            "near": [{"combo": c, "missing": m} for c, m in near[:50]],
        }

    def staples_for_colors(self, color_identity: set[str], limit: int = 50,
                           exclude: set[str] | None = None) -> list[tuple[str, int]]:
        """Top deck-frequency cards whose color identity fits, basics excluded."""
        exclude = exclude or set()
        out: list[tuple[str, int]] = []
        for cid, fq in self._staples:
            if cid in exclude:
                continue
            card = self._cards.get(cid)
            if card is None:
                continue
            if "Basic" in (card.get("type_line") or ""):
                continue
            if not set(card.get("color_identity") or []) <= color_identity:
                continue
            out.append((cid, fq))
            if len(out) >= limit:
                break
        return out

    # ---- SP5/SP4 neighbor reads (indexed, O(neighbors)) -------------------
    def cooccurrence_neighbors(self, card_id: str, limit: int = 30) -> list[tuple[str, float, float]]:
        """[(other_id, lift, jaccard)] ordered by lift desc."""
        rows = db.query(
            "SELECT b, lift, jaccard FROM card_cooccurrence WHERE a=%s "
            "ORDER BY lift DESC LIMIT %s", (card_id, limit))
        rows += db.query(
            "SELECT a, lift, jaccard FROM card_cooccurrence WHERE b=%s "
            "ORDER BY lift DESC LIMIT %s", (card_id, limit))
        rows.sort(key=lambda r: -(r[1] or 0.0))
        return [(r[0], r[1] or 0.0, r[2] or 0.0) for r in rows[:limit]]

    def synergy_neighbors(self, card_id: str, limit: int = 30) -> list[tuple[str, float]]:
        """[(other_id, max(synergy_ab, synergy_ba))] ordered desc."""
        rows = db.query(
            "SELECT b, synergy_ab, synergy_ba FROM card_relationships WHERE a=%s "
            "ORDER BY synergy_ab DESC LIMIT %s", (card_id, limit))
        rows += db.query(
            "SELECT a, synergy_ab, synergy_ba FROM card_relationships WHERE b=%s "
            "ORDER BY synergy_ba DESC LIMIT %s", (card_id, limit))
        best: dict[str, float] = {}
        for other, ab, ba in rows:
            v = max(ab or 0.0, ba or 0.0)
            if v > best.get(other, -1.0):
                best[other] = v
        return sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]

    def similarity_neighbors(self, card_id: str, limit: int = 30) -> list[tuple[str, float]]:
        """[(other_id, similarity)] ordered desc (per-card rows fetched via index, sorted here)."""
        rows = db.query(
            "SELECT b, similarity FROM card_relationships WHERE a=%s AND similarity > 0",
            (card_id,))
        rows += db.query(
            "SELECT a, similarity FROM card_relationships WHERE b=%s AND similarity > 0",
            (card_id,))
        rows.sort(key=lambda r: (-(r[1] or 0.0), r[0]))
        return [(r[0], r[1] or 0.0) for r in rows[:limit]]

    def engines_with(self, card_id: str) -> list[dict]:
        """Engines/combos containing card_id, asserted first then score desc."""
        engines = [self._engines[i] for i in self._engines_by_member.get(card_id, ())]
        engines.sort(key=lambda e: (not e["asserted"], -e["score"], e["engine_id"]))
        return engines

    # ---- semantic tag access -----------------------------------------------
    def _load_semantics(self) -> None:
        """Load per-ability and flat semantic tags from Postgres."""
        self._ability_tags: dict[str, list[list[str]]] = {}  # card_id -> [[tags per ability]]
        self._flat_tags_sem: dict[str, list[str]] = {}        # card_id -> flat union
        self._tag_inverted: dict[str, list[str]] = {}         # tag -> [card_ids]
        self._idf: dict[str, float] = {}                      # tag -> IDF weight
        # ability tags
        for card_id, _, tags_json in db.query(
                "SELECT card_id, ability_idx, tags FROM card_ability_tags "
                "ORDER BY card_id, ability_idx"):
            self._ability_tags.setdefault(card_id, []).append(json.loads(tags_json))
        # flat tags
        for card_id, tags_json in db.query("SELECT card_id, tags FROM card_flat_tags"):
            self._flat_tags_sem[card_id] = json.loads(tags_json)
        # inverted index
        for tag, ids_json in db.query("SELECT tag, card_ids FROM tag_inverted_index"):
            self._tag_inverted[tag] = json.loads(ids_json)
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
    return Store(config.CARDS_PATH)
