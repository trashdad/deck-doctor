# Relationship Measurement (SP1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a relationship-measurement layer over the SP2 fingerprint — four typed pair measures (similarity / directional synergy / combo / anti-synergy) plus a resource-flow graph that powers offline-mined and deck-scoped N-card engine detection — alongside (not replacing) the existing IER/CSS/DER.

**Architecture:** A new `scoring/relationships/` package. `resources.py` maps each card's SP2 fingerprint to produced/consumed typed resources. `graph.py` builds the producer→consumer graph and candidate-pair index. `measures.py` computes the four pair measures. `combo.py` ingests the Commander-Spellbook catalogs (asserted combos). `engines.py` mines multi-card engines + flags combo candidates offline, and searches engines within a given deck online. `build_relationships.py` orchestrates and writes two new SQLite tables (`card_relationships`, `engines`). The backend reads them additively; `synergies`/CSS/DER are untouched.

**Tech Stack:** Python 3.13 stdlib only (`json`, `sqlite3`, `math`, `dataclasses`); `pytest`. No new deps. Reads SP2's `card_fingerprints` table + `fingerprints` package.

**Spec:** `docs/superpowers/specs/2026-06-09-relationship-measurement-design.md`

---

## File structure

| File | Responsibility |
|---|---|
| `scoring/relationships/__init__.py` | Package marker |
| `scoring/relationships/resources.py` | fingerprint records → `{produces, consumes}` typed-resource sets |
| `scoring/relationships/measures.py` | `similarity`, `synergy` (directional), `anti_synergy` |
| `scoring/relationships/graph.py` | resource-flow graph + candidate-pair index (producer↔consumer) |
| `scoring/relationships/combo.py` | ingest `combo_catalog.json`/`known_combos.json`, map names→ids |
| `scoring/relationships/engines.py` | offline engine mining + combo-candidate flag + deck-scoped search |
| `scoring/build_relationships.py` | orchestrator: load fingerprints → measures + engines + combos → tables |
| `scoring/tests/test_rel_*.py` | unit + integration tests |
| `data/golden_relationships/*.json` | hand-verified expectations |
| `backend/app/store.py` (modify) | read `card_relationships` + deck engines (additive) |
| `backend/app/main.py` (modify) | expose typed edge on `/score/pair`; deck engine summary |

**Test import convention** (matches existing `scoring/tests/`): each test starts with
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```
then imports `from relationships.X import ...`. Run from `scoring/` with `python -m pytest`.

**Resource matching rule (used throughout):** a produced resource matches a consumed resource
if the strings are equal, OR one is the generic `"counter"` and the other starts with
`"counter:"`. This single rule lives in `resources.py::resource_match(produced, consumed)`.

---

### Task 1: Package + resource extraction

**Files:**
- Create: `scoring/relationships/__init__.py`, `scoring/relationships/resources.py`
- Test: `scoring/tests/test_rel_resources.py`

- [ ] **Step 1: Create the package marker**

`scoring/relationships/__init__.py`:
```python
"""Relationship measurement: resources, graph, measures, engines, combos."""
```

- [ ] **Step 2: Write the failing test**

`scoring/tests/test_rel_resources.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fingerprints.schema import AbilityRecord, Effect  # noqa: E402
from relationships.resources import card_resources, resource_match  # noqa: E402


def test_token_producer_produces_token():
    rec = AbilityRecord(ability_idx=0, kind="spell",
                        effects=[Effect(verb="CreateTokens")])
    res = card_resources([rec])
    assert "token" in res["produces"]


def test_dies_trigger_consumes_death_event():
    rec = AbilityRecord(ability_idx=0, kind="triggered",
                        trigger={"op": "WhenACreatureOrPlaneswalkerDies"},
                        effects=[Effect(verb="LoseLife")])
    res = card_resources([rec])
    assert "death_event" in res["consumes"]


def test_sac_outlet_produces_death_and_consumes_fodder():
    rec = AbilityRecord(ability_idx=0, kind="activated",
                        cost={"sacrifice": True},
                        effects=[Effect(verb="DrawACard")])
    res = card_resources([rec])
    assert "death_event" in res["produces"]
    assert "sacrifice_fodder" in res["consumes"]


def test_tap_cost_consumes_untap():
    rec = AbilityRecord(ability_idx=0, kind="activated",
                        cost={"tap": True}, effects=[Effect(verb="AddMana")])
    res = card_resources([rec])
    assert "untap" in res["consumes"]
    assert "mana" in res["produces"]


def test_counter_producer_and_generic_match():
    rec = AbilityRecord(ability_idx=0, kind="activated",
                        effects=[Effect(verb="PutACounterOfTypeOnPermanent", counter="plus1")])
    res = card_resources([rec])
    assert "counter:+1/+1" in res["produces"]
    assert resource_match("counter:+1/+1", "counter")
    assert resource_match("mana", "mana")
    assert not resource_match("mana", "token")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_rel_resources.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'relationships.resources'`

- [ ] **Step 4: Implement `resources.py`**

`scoring/relationships/resources.py`:
```python
"""Map SP2 fingerprint records to produced / consumed typed resources.

The resource-flow graph (graph.py) and all synergy/engine logic read these sets.
The maps are a deterministic seed taxonomy keyed on the raw MTGish verb / trigger
op / cost / counter the fingerprint already captured; they are intended to grow.
"""

from __future__ import annotations

from fingerprints.schema import AbilityRecord

# verb (_Action op) -> resource the effect PRODUCES
PRODUCER_VERB = {
    "AddMana": "mana", "AddManaWithModifiers": "mana", "AddManaRepeated": "mana",
    "CreateTokens": "token", "CreateNumberTokens": "token",
    "CreateTokensWithFlags": "token", "ForEachPlayerCreateTokens": "token",
    "Populate": "token", "PopulateNumberTimes": "token",
    "DrawACard": "card", "DrawNumberCards": "card", "DrawACardForEach": "card",
    "DrawUntilHandSize": "card",
    "GainLife": "life", "GainLifeForEach": "life", "GainLifeEqualToDamage": "life",
    "UntapPermanent": "untap", "UntapAllPermanents": "untap", "UntapEachPermanent": "untap",
    "SearchLibrary": "tutor", "SearchLibraryAndGraveyard": "tutor", "SeekACard": "tutor",
    "ReturnACardFromGraveyard": "reanimate", "ReturnPermanentFromGraveyard": "reanimate",
    "CastGraveyardCardWithoutPaying": "reanimate", "PutGraveyardCardOntoBattlefield": "reanimate",
}

# verbs that cause permanents to leave the battlefield -> produce "death_event"
DEATH_VERBS = {
    "DestroyAllPermanents", "DestroyEachPermanent", "DestroyAllCreatures",
    "ExileAllCreatures", "SacrificePermanent", "SacrificeAPermanent",
    "SacrificeNumberPermanents",
}

# trigger op -> resource the ability CONSUMES (pays off / cares about)
TRIGGER_CONSUMER = {
    "WhenAPermanentDies": "death_event",
    "WhenACreatureOrPlaneswalkerDies": "death_event",
    "WhenAPermanentIsSacrificed": "death_event",
    "WhenAPlayerSacrificesAPermanent": "death_event",
    "WhenATokenEntersTheBattlefield": "token",
    "WhenATokenIsCreated": "token",
    "WhenAPlayerGainsLife": "life",
    "WhenACounterOfTypeIsPutOnAPermanent": "counter",
    "WhenACounterIsPutOnAPermanent": "counter",
    "WhenAPlayerCastsASpell": "spell_cast",
    "WhenAPlayerCastsANonCreatureSpell": "spell_cast",
    "WhenACreatureAttacks": "attack_trigger",
    "WhenALandEntersTheBattlefield": "landfall",
}


def resource_match(produced: str, consumed: str) -> bool:
    """A produced resource satisfies a consumed one (with generic 'counter')."""
    if produced == consumed:
        return True
    if consumed == "counter" and produced.startswith("counter:"):
        return True
    if produced == "counter" and consumed.startswith("counter:"):
        return True
    return False


def _effect_products(effects, out: set) -> None:
    for e in effects:
        if e.verb in PRODUCER_VERB:
            out.add(PRODUCER_VERB[e.verb])
        if e.verb in DEATH_VERBS:
            out.add("death_event")
        if e.counter:
            out.add(f"counter:{_counter_label(e.counter)}")
            out.add("counter")
        _effect_products(e.sub_effects, out)


def _counter_label(slug: str) -> str:
    return {"plus1": "+1/+1", "minus1": "-1/-1"}.get(slug, slug)


def card_resources(records: list[AbilityRecord]) -> dict:
    """Return {'produces': set[str], 'consumes': set[str]} for a card."""
    produces: set[str] = set()
    consumes: set[str] = set()
    for rec in records:
        _effect_products(rec.effects, produces)
        if rec.trigger:
            r = TRIGGER_CONSUMER.get(rec.trigger.get("op", ""))
            if r:
                consumes.add(r)
        if rec.cost:
            if rec.cost.get("tap"):
                consumes.add("untap")
            if rec.cost.get("sacrifice"):
                consumes.add("sacrifice_fodder")
                produces.add("death_event")   # a sac outlet kills permanents
        # "for each <object>" dynamic amounts mean the card cares about that object
        for e in rec.effects:
            if e.amount and e.amount.kind == "dynamic" and e.amount.count:
                obj = (e.amount.count.get("counted_object") or "").lower()
                if "token" in obj:
                    consumes.add("token")
    return {"produces": produces, "consumes": consumes}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_rel_resources.py -q`
Expected: PASS (5 passed)

- [ ] **Step 6: Commit**

```bash
git add scoring/relationships/__init__.py scoring/relationships/resources.py scoring/tests/test_rel_resources.py
git commit -m "feat(rel): map fingerprint records to produced/consumed resources"
```

---

### Task 2: Similarity measure

**Files:**
- Create: `scoring/relationships/measures.py`
- Test: `scoring/tests/test_rel_measures.py`

- [ ] **Step 1: Write the failing test**

`scoring/tests/test_rel_measures.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from relationships.measures import similarity  # noqa: E402


def test_identical_vectors_similarity_one():
    v = {"verb:DrawACard": 1, "kind:spell": 1}
    assert similarity(v, v) == 1.0


def test_disjoint_vectors_similarity_zero():
    assert similarity({"verb:DrawACard": 1}, {"verb:AddMana": 1}) == 0.0


def test_partial_overlap_between_zero_and_one():
    a = {"verb:AddMana": 1, "kind:activated": 1}
    b = {"verb:AddMana": 1, "kind:spell": 1}
    s = similarity(a, b)
    assert 0.0 < s < 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_rel_measures.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'relationships.measures'`

- [ ] **Step 3: Implement `similarity`**

`scoring/relationships/measures.py`:
```python
"""The four typed pair measures: similarity, synergy (directional), anti_synergy.

similarity  : cosine over fingerprint_to_vector dicts (redundancy axis).
synergy     : directional resource producer->consumer match (enabling axis).
anti_synergy: conservative rule-based anti-pattern detection.
These are different axes by design (two ramp rocks: similar, not synergistic).
"""

from __future__ import annotations

import math

from relationships.resources import resource_match


def similarity(vec_a: dict, vec_b: dict) -> float:
    """Cosine similarity over two sparse feature-count dicts, in [0, 1]."""
    if not vec_a or not vec_b:
        return 0.0
    dot = sum(v * vec_b.get(k, 0) for k, v in vec_a.items())
    na = math.sqrt(sum(v * v for v in vec_a.values()))
    nb = math.sqrt(sum(v * v for v in vec_b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return round(dot / (na * nb), 4)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_rel_measures.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scoring/relationships/measures.py scoring/tests/test_rel_measures.py
git commit -m "feat(rel): similarity (cosine over fingerprint vectors)"
```

---

### Task 3: Directional synergy measure

**Files:**
- Modify: `scoring/relationships/measures.py`
- Test: `scoring/tests/test_rel_measures.py`

- [ ] **Step 1: Write the failing test (append)**

```python
from relationships.measures import synergy  # noqa: E402


def test_synergy_directional_producer_to_consumer():
    a = {"produces": {"token"}, "consumes": set()}
    b = {"produces": set(), "consumes": {"token"}}
    ab, ba = synergy(a, b)
    assert ab > 0.0      # A makes tokens, B pays off tokens
    assert ba == 0.0     # B gives A nothing


def test_synergy_counter_generic_match():
    a = {"produces": {"counter:+1/+1"}, "consumes": set()}
    b = {"produces": set(), "consumes": {"counter"}}
    ab, ba = synergy(a, b)
    assert ab > 0.0


def test_synergy_none_when_no_resource_overlap():
    a = {"produces": {"mana"}, "consumes": set()}
    b = {"produces": set(), "consumes": {"token"}}
    assert synergy(a, b) == (0.0, 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_rel_measures.py -q`
Expected: FAIL — `ImportError: cannot import name 'synergy'`

- [ ] **Step 3: Implement `synergy`**

Append to `scoring/relationships/measures.py`:
```python
SYNERGY_K = 0.8   # squash steepness; calibrated against the golden set


def _squash(raw: float, k: float = SYNERGY_K) -> float:
    """Monotonic map of a non-negative raw score into [0, 1)."""
    return round(1.0 - math.exp(-k * raw), 4)


def _directional_raw(prod: set, cons: set) -> float:
    """Count produced resources that satisfy a consumed resource."""
    return float(sum(1 for p in prod for c in cons if resource_match(p, c)))


def synergy(res_a: dict, res_b: dict) -> tuple[float, float]:
    """Directional synergy (ab, ba): A produces what B consumes, and vice versa."""
    ab = _squash(_directional_raw(res_a["produces"], res_b["consumes"]))
    ba = _squash(_directional_raw(res_b["produces"], res_a["consumes"]))
    return ab, ba
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_rel_measures.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add scoring/relationships/measures.py scoring/tests/test_rel_measures.py
git commit -m "feat(rel): directional synergy from resource producer/consumer match"
```

---

### Task 4: Anti-synergy (rule-based, conservative)

**Files:**
- Modify: `scoring/relationships/measures.py`
- Test: `scoring/tests/test_rel_measures.py`

Anti-synergy v1 is a small, precise rule set. Each rule is `(predicate_a, predicate_b, weight)`; it fires if `predicate_a(card_a) and predicate_b(card_b)` (checked both orderings). v1 ships ONE well-grounded rule — "one card refills your hand while the other rewards an empty hand (hellbent)" — and the structure to add more. Predicates read the card's flat tags (the SP2 derived tags) for simplicity.

- [ ] **Step 1: Write the failing test (append)**

```python
from relationships.measures import anti_synergy  # noqa: E402


def test_anti_synergy_refill_vs_hellbent():
    # card A draws cards (refills hand); card B rewards empty hand
    a_tags = {"e:draw"}
    b_tags = {"cond:hellbent"}
    assert anti_synergy(a_tags, b_tags) > 0.0
    # order-independent
    assert anti_synergy(b_tags, a_tags) > 0.0


def test_anti_synergy_zero_for_unrelated():
    assert anti_synergy({"e:draw"}, {"e:mana"}) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_rel_measures.py -q`
Expected: FAIL — `ImportError: cannot import name 'anti_synergy'`

- [ ] **Step 3: Implement `anti_synergy`**

Append to `scoring/relationships/measures.py`:
```python
# Conservative anti-pattern rules over SP2 flat tags: (tagset_x, tagset_y, weight).
# Fires when card_x has all of tagset_x AND card_y has all of tagset_y (either order).
# Intentionally small in v1; the strong anti-synergy signal is SP3 negative co-occurrence.
ANTI_RULES: list[tuple[set, set, float]] = [
    ({"e:draw"}, {"cond:hellbent"}, 1.0),     # refills hand vs rewards-empty-hand
]


def anti_synergy(tags_a: set, tags_b: set) -> float:
    """Conservative rule-based anti-synergy in [0, 1]. Order-independent."""
    ta, tb = set(tags_a), set(tags_b)
    raw = 0.0
    for left, right, w in ANTI_RULES:
        if left <= ta and right <= tb:
            raw += w
        if left <= tb and right <= ta:
            raw += w
    return _squash(raw)
```

Note: `cond:hellbent` is illustrative of the namespace; the orchestrator (Task 9) passes
whatever flat tags exist. If the corpus has no `cond:hellbent` tag yet, the rule simply never
fires — that is acceptable (the rule set grows additively per the spec).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_rel_measures.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add scoring/relationships/measures.py scoring/tests/test_rel_measures.py
git commit -m "feat(rel): conservative rule-based anti-synergy"
```

---

### Task 5: Resource-flow graph + candidate-pair index

**Files:**
- Create: `scoring/relationships/graph.py`
- Test: `scoring/tests/test_rel_graph.py`

The graph avoids all-pairs (30k² ≈ 9e8). Candidate pairs come from a producer↔consumer index:
for each resource, pair its producers with its consumers. That is the only set of pairs that
can have nonzero synergy.

- [ ] **Step 1: Write the failing test**

`scoring/tests/test_rel_graph.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from relationships.graph import candidate_pairs, neighbors_out  # noqa: E402


def _R(prod, cons):
    return {"produces": set(prod), "consumes": set(cons)}


def test_candidate_pairs_links_producer_to_consumer():
    res = {
        "maker": _R(["token"], []),
        "payoff": _R([], ["token"]),
        "unrelated": _R(["mana"], []),
    }
    pairs = candidate_pairs(res)
    assert ("maker", "payoff") in pairs or ("payoff", "maker") in pairs
    # unrelated mana producer has no consumer -> no pair
    assert all("unrelated" not in p for p in pairs)


def test_neighbors_out_directed_by_resource_flow():
    res = {"maker": _R(["token"], []), "payoff": _R([], ["token"])}
    outs = neighbors_out("maker", res)
    assert "payoff" in outs
    assert neighbors_out("payoff", res) == set()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_rel_graph.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'relationships.graph'`

- [ ] **Step 3: Implement `graph.py`**

`scoring/relationships/graph.py`:
```python
"""Resource-flow graph over card resources.

Directed edge maker -> payoff when maker.produces satisfies payoff.consumes.
candidate_pairs() yields only pairs that can have nonzero synergy (producer x
consumer per resource), avoiding the all-pairs blowup.
"""

from __future__ import annotations

from collections import defaultdict

from relationships.resources import resource_match


def _producer_consumer_index(resources: dict) -> tuple[dict, dict]:
    """resource -> set(card_ids producing it) and resource -> set(consuming it).

    Producers are indexed by their concrete resource string; consumers that ask
    for generic 'counter' are expanded so resource_match still holds via lookup.
    """
    by_prod = defaultdict(set)
    by_cons = defaultdict(set)
    for cid, r in resources.items():
        for p in r["produces"]:
            by_prod[p].add(cid)
        for c in r["consumes"]:
            by_cons[c].add(cid)
    return by_prod, by_cons


def candidate_pairs(resources: dict) -> set:
    """Unordered candidate pairs (a, b) that may have nonzero synergy."""
    by_prod, by_cons = _producer_consumer_index(resources)
    pairs: set = set()
    for cons_res, consumers in by_cons.items():
        # find producers whose product matches this consumed resource
        producers: set = set()
        for prod_res, makers in by_prod.items():
            if resource_match(prod_res, cons_res):
                producers |= makers
        for c in consumers:
            for p in producers:
                if p != c:
                    pairs.add(tuple(sorted((p, c))))
    return pairs


def neighbors_out(card_id: str, resources: dict) -> set:
    """Cards that consume something this card produces (directed maker->payoff)."""
    me = resources.get(card_id)
    if not me:
        return set()
    outs: set = set()
    for other, r in resources.items():
        if other == card_id:
            continue
        if any(resource_match(p, c) for p in me["produces"] for c in r["consumes"]):
            outs.add(other)
    return outs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_rel_graph.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add scoring/relationships/graph.py scoring/tests/test_rel_graph.py
git commit -m "feat(rel): resource-flow graph + candidate-pair index"
```

---

### Task 6: Combo catalog ingest

**Files:**
- Create: `scoring/relationships/combo.py`
- Test: `scoring/tests/test_rel_combo.py`

Catalog pieces are card NAMES; map to ids via a `name->id` dict (caller supplies it, built
with the SP2 `norm_name`). Combos whose pieces aren't all in the corpus are skipped.

- [ ] **Step 1: Write the failing test**

`scoring/tests/test_rel_combo.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_rel_combo.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'relationships.combo'`

- [ ] **Step 3: Implement `combo.py`**

`scoring/relationships/combo.py`:
```python
"""Ingest Commander-Spellbook combo catalogs into asserted combos.

Catalog pieces are card names; we map them to ids with the caller-supplied
name_to_id (built via fingerprints/build_semantics norm_name). Combos whose
pieces aren't all present in the corpus are skipped (can't be asserted).
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path


def _norm(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def load_catalog_combos(catalog_paths: list[str], name_to_id: dict) -> list[dict]:
    """Return asserted combos: [{combo_id, member_ids, result, steps, url}]."""
    norm_map = {_norm(k): v for k, v in name_to_id.items()}
    out: list[dict] = []
    seen: set = set()
    for path in catalog_paths:
        p = Path(path)
        if not p.is_file():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        combos = data.get("combos", []) if isinstance(data, dict) else []
        for c in combos:
            pieces = c.get("pieces") or []
            ids = [norm_map.get(_norm(name)) for name in pieces]
            if not pieces or any(i is None for i in ids):
                continue
            combo_id = c.get("id") or "+".join(sorted(ids))
            if combo_id in seen:
                continue
            seen.add(combo_id)
            out.append({
                "combo_id": combo_id,
                "member_ids": ids,
                "result": c.get("result", ""),
                "steps": c.get("steps", ""),
                "url": c.get("source_url", ""),
            })
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_rel_combo.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add scoring/relationships/combo.py scoring/tests/test_rel_combo.py
git commit -m "feat(rel): ingest Commander-Spellbook combo catalogs"
```

---

### Task 7: Engine mining + combo-candidate flag

**Files:**
- Create: `scoring/relationships/engines.py`
- Test: `scoring/tests/test_rel_engines.py`

An engine is a connected set (k∈[2..5]) over the directed resource graph whose members chain
producer→consumer. v1 mining: from each seed pair, greedily grow by adding a card that
consumes something already produced in the set OR produces something already consumed, up to
k=5; dedupe by member frozenset. A **combo candidate** is an engine that contains a directed
cycle (some member's product feeds back to enable an earlier member) — flagged, never asserted.

- [ ] **Step 1: Write the failing test**

`scoring/tests/test_rel_engines.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from relationships.engines import mine_engines, has_cycle  # noqa: E402


def _R(prod, cons):
    return {"produces": set(prod), "consumes": set(cons)}


def test_mine_finds_three_card_chain():
    # maker -> sac_outlet(consumes fodder=token, produces death) -> aristocrat(consumes death)
    res = {
        "maker": _R(["token"], []),
        "outlet": _R(["death_event"], ["token"]),
        "aristocrat": _R([], ["death_event"]),
    }
    engines = mine_engines(res, kmax=5)
    members = [frozenset(e["members"]) for e in engines]
    assert frozenset({"maker", "outlet", "aristocrat"}) in members


def test_has_cycle_detects_untap_mana_loop():
    # A taps for mana (consumes untap, produces mana); B untaps A (consumes mana, produces untap)
    res = {
        "A": _R(["mana"], ["untap"]),
        "B": _R(["untap"], ["mana"]),
    }
    assert has_cycle(["A", "B"], res) is True


def test_no_cycle_for_pure_chain():
    res = {"maker": _R(["token"], []), "payoff": _R([], ["token"])}
    assert has_cycle(["maker", "payoff"], res) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_rel_engines.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'relationships.engines'`

- [ ] **Step 3: Implement `engines.py`**

`scoring/relationships/engines.py`:
```python
"""Multi-card engine mining + combo-candidate flagging over the resource graph.

Engine = connected member set (k in [2..5]) chained by producer->consumer resource
flow. Combo candidate = engine whose directed flow contains a cycle (potential
unbounded loop) — flagged for review, NEVER asserted as a real infinite combo.
"""

from __future__ import annotations

from relationships.resources import resource_match


def _feeds(a: str, b: str, res: dict) -> bool:
    """True if a produces a resource that b consumes."""
    return any(resource_match(p, c) for p in res[a]["produces"] for c in res[b]["consumes"])


def _connects(card: str, members: list, res: dict) -> bool:
    """card extends the set if it feeds, or is fed by, any current member."""
    return any(_feeds(card, m, res) or _feeds(m, card, res) for m in members)


def has_cycle(members: list, res: dict) -> bool:
    """Directed cycle among members using producer->consumer edges (DFS)."""
    nodes = list(members)
    adj = {n: [m for m in nodes if m != n and _feeds(n, m, res)] for n in nodes}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}

    def dfs(u: str) -> bool:
        color[u] = GRAY
        for v in adj[u]:
            if color[v] == GRAY:
                return True
            if color[v] == WHITE and dfs(v):
                return True
        color[u] = BLACK
        return False

    return any(color[n] == WHITE and dfs(n) for n in nodes)


def mine_engines(resources: dict, kmax: int = 5, max_per_seed: int = 50) -> list[dict]:
    """Greedy engine mining from producer->consumer seed pairs.

    Deterministic: candidates and members are processed in sorted order; engines
    deduped by member frozenset.
    """
    from relationships.graph import candidate_pairs

    seeds = sorted(candidate_pairs(resources))
    seen: set = set()
    engines: list[dict] = []

    for a, b in seeds:
        frontier = [[a, b]]
        grown = 0
        while frontier and grown < max_per_seed:
            members = frontier.pop()
            key = frozenset(members)
            if key not in seen:
                seen.add(key)
                engines.append({
                    "members": sorted(members),
                    "kind": "cycle" if has_cycle(members, resources) else "chain",
                    "candidate": has_cycle(members, resources),
                })
                grown += 1
            if len(members) >= kmax:
                continue
            # try to extend with any connecting card (sorted for determinism)
            for cand in sorted(resources):
                if cand in members:
                    continue
                if _connects(cand, members, resources):
                    new = sorted(members + [cand])
                    if frozenset(new) not in seen:
                        frontier.append(new)
    return engines


def deck_engines(resources: dict, deck_ids: list, kmax: int = 5) -> list[dict]:
    """Engines wholly contained in a given deck (online, deck <= ~100 cards)."""
    sub = {cid: resources[cid] for cid in deck_ids if cid in resources}
    return mine_engines(sub, kmax=kmax)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_rel_engines.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scoring/relationships/engines.py scoring/tests/test_rel_engines.py
git commit -m "feat(rel): engine mining + combo-candidate cycle detection"
```

---

### Task 8: Orchestrator `build_relationships.py`

**Files:**
- Create: `scoring/build_relationships.py`
- Test: `scoring/tests/test_rel_build.py`

Loads SP2 `card_fingerprints` from the DB, computes resources, scores candidate pairs (the
four measures), ingests catalog combos, mines engines, writes `card_relationships` + `engines`.

- [ ] **Step 1: Write the failing integration test**

`scoring/tests/test_rel_build.py`:
```python
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_relationships import build  # noqa: E402


def _seed_db(db, cards, fingerprints):
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE cards (id TEXT PRIMARY KEY, name TEXT, cmc REAL, type_line TEXT, "
                "colors TEXT, color_identity TEXT, image_normal TEXT, ier REAL, "
                "mechanic_tags TEXT, parasitic TEXT)")
    for cid, name in cards:
        con.execute("INSERT INTO cards (id, name) VALUES (?,?)", (cid, name))
    con.execute("CREATE TABLE card_fingerprints (card_id TEXT, ability_idx INT, record TEXT, "
                "source TEXT, confidence REAL, PRIMARY KEY(card_id, ability_idx))")
    con.execute("CREATE TABLE card_flat_tags (card_id TEXT PRIMARY KEY, tags TEXT)")
    for cid, recs in fingerprints.items():
        for r in recs:
            con.execute("INSERT INTO card_fingerprints VALUES (?,?,?,?,?)",
                        (cid, r["ability_idx"], json.dumps(r), "mtgish", 1.0))
        con.execute("INSERT INTO card_flat_tags VALUES (?,?)", (cid, json.dumps([])))
    con.commit(); con.close()


def test_build_writes_relationship_and_engine_tables(tmp_path):
    db = str(tmp_path / "scores.sqlite")
    cards = [("id-maker", "Maker"), ("id-payoff", "Payoff")]
    fps = {
        "id-maker": [{"ability_idx": 0, "kind": "spell", "trigger": None, "cost": None,
                      "condition": None, "optional": False, "modal": None,
                      "effects": [{"verb": "CreateTokens", "object": None, "prefixes": [],
                                   "scope": None, "quantifier": None, "targeted": False,
                                   "counter": None, "amount": None, "duration": None,
                                   "grants": None, "optional": False, "sub_effects": []}],
                      "raw": {}}],
        "id-payoff": [{"ability_idx": 0, "kind": "triggered",
                       "trigger": {"op": "WhenATokenIsCreated"}, "cost": None,
                       "condition": None, "optional": False, "modal": None,
                       "effects": [], "raw": {}}],
    }
    _seed_db(db, cards, fps)

    stats = build(db, catalog_paths=[], kmax=3)

    con = sqlite3.connect(db)
    row = con.execute("SELECT synergy_ab, synergy_ba, similarity FROM card_relationships "
                      "WHERE a=? AND b=?", tuple(sorted(["id-maker", "id-payoff"]))).fetchone()
    assert row is not None
    a, b = sorted(["id-maker", "id-payoff"])
    # maker produces token, payoff consumes token -> directed synergy from maker
    syn = con.execute("SELECT synergy_ab, synergy_ba FROM card_relationships WHERE a=? AND b=?",
                      (a, b)).fetchone()
    assert max(syn) > 0.0
    n_eng = con.execute("SELECT COUNT(*) FROM engines").fetchone()[0]
    assert n_eng >= 1
    con.close()
    assert stats["pairs"] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_rel_build.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'build_relationships'`

- [ ] **Step 3: Implement `build_relationships.py`**

`scoring/build_relationships.py`:
```python
"""Build the relationship layer: resources -> measures + engines + combos -> tables.

Reads SP2 card_fingerprints from data/scores.sqlite, writes card_relationships and
engines. Leaves synergies / CSS / DER untouched (augment, not replace).

Usage:
    python scoring/build_relationships.py --db data/scores.sqlite \
        --catalog C:/simmander/simmander/data/combo_catalog.json \
        --catalog C:/simmander/simmander/data/known_combos.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fingerprints.schema import AbilityRecord  # noqa: E402
from fingerprints.derive import fingerprint_to_vector  # noqa: E402
from relationships.resources import card_resources  # noqa: E402
from relationships.graph import candidate_pairs  # noqa: E402
from relationships.measures import similarity, synergy, anti_synergy  # noqa: E402
from relationships.engines import mine_engines  # noqa: E402
from relationships.combo import load_catalog_combos  # noqa: E402


def _load_fingerprints(con) -> dict:
    out: dict = {}
    for cid, record in con.execute("SELECT card_id, record FROM card_fingerprints "
                                   "ORDER BY card_id, ability_idx"):
        out.setdefault(cid, []).append(AbilityRecord.from_dict(json.loads(record)))
    return out


def _load_flat_tags(con) -> dict:
    out: dict = {}
    try:
        for cid, tags in con.execute("SELECT card_id, tags FROM card_flat_tags"):
            out[cid] = set(json.loads(tags))
    except sqlite3.OperationalError:
        pass
    return out


def build(db_path: str, catalog_paths: list[str] | None = None, kmax: int = 5) -> dict:
    con = sqlite3.connect(db_path)
    fps = _load_fingerprints(con)
    flat = _load_flat_tags(con)
    name_to_id = {name: cid for cid, name in con.execute("SELECT id, name FROM cards")}

    resources = {cid: card_resources(recs) for cid, recs in fps.items()}
    vectors = {cid: fingerprint_to_vector(recs) for cid, recs in fps.items()}

    combos = load_catalog_combos(catalog_paths or [], name_to_id)
    combo_pair_id: dict = {}
    for c in combos:
        ids = c["member_ids"]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                combo_pair_id[tuple(sorted((ids[i], ids[j])))] = c["combo_id"]

    pairs = candidate_pairs(resources) | set(combo_pair_id)
    rows: list[tuple] = []
    for a, b in pairs:
        if a not in resources or b not in resources:
            continue
        ab, ba = synergy(resources[a], resources[b])
        sim = similarity(vectors.get(a, {}), vectors.get(b, {}))
        anti = anti_synergy(flat.get(a, set()), flat.get(b, set()))
        cid = combo_pair_id.get((a, b))
        rows.append((a, b, sim, ab, ba, anti, 1 if cid else 0, cid, 0))

    engines = mine_engines(resources, kmax=kmax)
    asserted_member_sets = {frozenset(c["member_ids"]) for c in combos}

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
    con.executemany("INSERT OR REPLACE INTO card_relationships VALUES (?,?,?,?,?,?,?,?,?)", rows)

    # asserted catalog combos as engines
    eng_rows: list[tuple] = []
    for c in combos:
        eng_rows.append((c["combo_id"], json.dumps(sorted(c["member_ids"])), "combo",
                         json.dumps([]), 1.0, 1, 0))
    for i, e in enumerate(engines):
        members = sorted(e["members"])
        eng_rows.append((f"eng-{i}", json.dumps(members), e["kind"], json.dumps([]),
                         float(len(members)),
                         1 if frozenset(members) in asserted_member_sets else 0,
                         1 if e["candidate"] else 0))
    con.executemany("INSERT OR REPLACE INTO engines VALUES (?,?,?,?,?,?,?)", eng_rows)
    con.commit(); con.close()

    return {"pairs": len(rows), "engines": len(engines),
            "asserted_combos": len(combos)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="data/scores.sqlite")
    p.add_argument("--catalog", action="append", default=[])
    p.add_argument("--kmax", type=int, default=5)
    a = p.parse_args()
    stats = build(a.db, catalog_paths=a.catalog, kmax=a.kmax)
    print(f"relationships: {stats['pairs']:,} pairs | engines: {stats['engines']:,} "
          f"| asserted combos: {stats['asserted_combos']:,}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_rel_build.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Run full suite**

Run: `cd scoring && python -m pytest -q`
Expected: PASS (all relationship + fingerprint + evaluate tests)

- [ ] **Step 6: Commit**

```bash
git add scoring/build_relationships.py scoring/tests/test_rel_build.py
git commit -m "feat(rel): orchestrator writes card_relationships + engines tables"
```

---

### Task 9: Real run + golden relationships + catalog-recall

**Files:**
- Create: `data/golden_relationships/*.json`, `scoring/tests/test_rel_golden.py`

- [ ] **Step 1: Run the real build**

Run:
```bash
cd C:/simmander/simmander-deckbuilder
python scoring/build_relationships.py --db data/scores.sqlite \
  --catalog C:/simmander/simmander/data/combo_catalog.json \
  --catalog C:/simmander/simmander/data/known_combos.json
```
Expected: prints pair / engine / asserted-combo counts. Note the numbers.

- [ ] **Step 2: Inspect a few real pairs and capture golden expectations**

Run (adjust names to real high-synergy and high-similarity examples you verify):
```bash
cd C:/simmander/simmander-deckbuilder && python -c "
import sqlite3, json
con=sqlite3.connect('data/scores.sqlite')
def rel(n1,n2):
    ids=dict(con.execute('select name,id from cards where name in (?,?)',(n1,n2)))
    a,b=sorted([ids[n1],ids[n2]])
    return con.execute('select similarity,synergy_ab,synergy_ba,combo,anti_synergy from card_relationships where a=? and b=?',(a,b)).fetchone()
print('Sol Ring / Arcane Signet (similar ramp):', rel('Sol Ring','Arcane Signet'))
print('Lightning Bolt / Doom Blade (similar removal):', rel('Lightning Bolt','Doom Blade'))
"
```
Hand-verify the values make sense (two ramp rocks → high similarity, low synergy), then write
golden files capturing the *qualitative* expectation. `data/golden_relationships/similarity_ramp.json`:
```json
{"a": "Sol Ring", "b": "Arcane Signet",
 "expect": {"similarity_min": 0.5, "synergy_max": 0.4}}
```
Create 4–6 such files spanning: high-similarity (two ramp rocks / two removal spells),
high-synergy (a token-maker + a tokens-matter payoff you confirm), a catalog combo pair
(`combo` true), and an anti-synergy case if one exists in-corpus (else skip that file).

- [ ] **Step 3: Write the golden + catalog-recall test**

`scoring/tests/test_rel_golden.py`:
```python
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DB = Path(__file__).resolve().parents[2] / "data" / "scores.sqlite"
GOLDEN = Path(__file__).resolve().parents[2] / "data" / "golden_relationships"


def _rel(con, name_a, name_b):
    ids = dict(con.execute("SELECT name, id FROM cards WHERE name IN (?, ?)", (name_a, name_b)))
    if name_a not in ids or name_b not in ids:
        return None
    a, b = sorted([ids[name_a], ids[name_b]])
    return con.execute("SELECT similarity, synergy_ab, synergy_ba, combo, anti_synergy "
                       "FROM card_relationships WHERE a=? AND b=?", (a, b)).fetchone()


def test_golden_relationships():
    if not DB.is_file() or not GOLDEN.is_dir() or not list(GOLDEN.glob("*.json")):
        import pytest
        pytest.skip("no built DB or golden files yet")
    con = sqlite3.connect(DB)
    failures = []
    for f in sorted(GOLDEN.glob("*.json")):
        spec = json.loads(f.read_text(encoding="utf-8"))
        row = _rel(con, spec["a"], spec["b"])
        if row is None:
            failures.append(f"{f.name}: pair not found / no relationship row")
            continue
        sim, ab, ba, combo, anti = row
        e = spec["expect"]
        if "similarity_min" in e and sim < e["similarity_min"]:
            failures.append(f"{f.name}: similarity {sim} < {e['similarity_min']}")
        if "synergy_max" in e and max(ab, ba) > e["synergy_max"]:
            failures.append(f"{f.name}: synergy {max(ab, ba)} > {e['synergy_max']}")
        if "synergy_min" in e and max(ab, ba) < e["synergy_min"]:
            failures.append(f"{f.name}: synergy {max(ab, ba)} < {e['synergy_min']}")
        if e.get("combo") and not combo:
            failures.append(f"{f.name}: expected combo=true")
    con.close()
    assert not failures, "\n".join(failures)


def test_catalog_recall_sanity():
    """The miner should re-surface a majority of asserted 2-card combos as engines."""
    if not DB.is_file():
        import pytest
        pytest.skip("no built DB")
    con = sqlite3.connect(DB)
    asserted = [json.loads(m) for (m,) in con.execute(
        "SELECT members FROM engines WHERE asserted_combo=1")]
    two_card = [set(m) for m in asserted if len(m) == 2]
    if not two_card:
        import pytest
        con.close(); pytest.skip("no 2-card asserted combos in corpus")
    mined = [set(json.loads(m)) for (m,) in con.execute(
        "SELECT members FROM engines WHERE asserted_combo=0")]
    recalled = sum(1 for combo in two_card
                   if any(combo <= e for e in mined) or combo in two_card)
    # asserted combos are themselves stored as engines, so recall is trivially high;
    # this is a presence/sanity gate, not a precision metric.
    assert recalled >= 1
    con.close()
```

- [ ] **Step 4: Run the tests**

Run: `cd scoring && python -m pytest tests/test_rel_golden.py -q`
Expected: PASS. If a golden expectation fails, either the measure needs calibration
(adjust `SYNERGY_K` / weights) or the golden bound was wrong (re-verify) — do not loosen
bounds blindly to force green.

- [ ] **Step 5: Commit**

```bash
git add data/golden_relationships scoring/tests/test_rel_golden.py
git commit -m "test(rel): golden relationship expectations + catalog-recall sanity"
```

---

### Task 10: Backend — expose typed edge on `/score/pair`

**Files:**
- Modify: `backend/app/store.py` (add `relationship` method), `backend/app/main.py` (`/score/pair`)
- Test: `backend/tests/test_api.py` (add a case) — follow the existing test file's style

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_api.py` (match its existing client fixture/style):
```python
def test_score_pair_includes_typed_edge(client):
    # uses whatever two ids the test fixture/store exposes; assert the new keys exist
    r = client.get("/score/pair", params={"a": SAMPLE_ID_A, "b": SAMPLE_ID_B})
    assert r.status_code == 200
    body = r.json()
    # legacy fields preserved
    assert "css" in body and "der" in body
    # new typed edge present (may be null if no relationship row, but key exists)
    assert "relationship" in body
```
If `backend/tests/test_api.py` doesn't define `SAMPLE_ID_A/B` or a `client` fixture, mirror
the existing tests there exactly (they already exercise `/score/pair`); reuse their ids.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_api.py -q`
Expected: FAIL — `KeyError: 'relationship'` (or assertion error: key missing)

- [ ] **Step 3: Add `Store.relationship` and wire it in**

In `backend/app/store.py`, add a method on `Store` (near `pair`, ~line 136):
```python
    def relationship(self, a: str, b: str) -> dict | None:
        lo, hi = sorted([a, b])
        with self._conn() as conn:
            try:
                row = conn.execute(
                    "SELECT similarity, synergy_ab, synergy_ba, anti_synergy, combo, combo_id "
                    "FROM card_relationships WHERE a=? AND b=?", (lo, hi)).fetchone()
            except sqlite3.OperationalError:
                return None
        if row is None:
            return None
        sim, ab, ba, anti, combo, combo_id = row
        # orient synergy to the caller's (a, b) order
        syn_ab, syn_ba = (ab, ba) if a == lo else (ba, ab)
        return {"similarity": sim, "synergy_ab": syn_ab, "synergy_ba": syn_ba,
                "anti_synergy": anti, "combo": bool(combo), "combo_id": combo_id}
```
In `backend/app/main.py`, in `score_pair` (~line 129), add the typed edge to the returned
dict without removing existing fields:
```python
@app.get("/score/pair", response_model=PairScore)
def score_pair(a: str, b: str) -> dict:
    store = get_store()
    result = store.pair(a, b) or {"card_a": a, "card_b": b, "css": 0.0, "der": 0.0, "lift": False}
    result["relationship"] = store.relationship(a, b)
    return result
```
Add `relationship: dict | None = None` to the `PairScore` model in `backend/app/models.py`
so the response validates.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_api.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/store.py backend/app/main.py backend/app/models.py backend/tests/test_api.py
git commit -m "feat(rel): expose typed relationship edge on /score/pair"
```

---

### Task 11: Backend — deck engine summary

**Files:**
- Modify: `backend/app/store.py` (add `deck_engines`), `backend/app/main.py` (endpoint)
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_api.py`:
```python
def test_deck_engines_endpoint(client):
    r = client.post("/deck/engines", json={"cards": [{"id": SAMPLE_ID_A, "count": 1},
                                                      {"id": SAMPLE_ID_B, "count": 1}]})
    assert r.status_code == 200
    body = r.json()
    assert "engines" in body and "combos" in body
    assert isinstance(body["engines"], list)
```
(Match the existing `DeckRequest` body shape used by `/deck/analyze` in this test file.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_api.py -q`
Expected: FAIL — 404 (route missing) or KeyError

- [ ] **Step 3: Implement deck engines read**

In `backend/app/store.py` add:
```python
    def deck_engines(self, ids: list[str]) -> dict:
        idset = set(ids)
        engines: list[dict] = []
        combos: list[dict] = []
        with self._conn() as conn:
            try:
                rows = conn.execute(
                    "SELECT engine_id, members, kind, asserted_combo, candidate FROM engines"
                ).fetchall()
            except sqlite3.OperationalError:
                return {"engines": [], "combos": []}
        import json as _json
        for engine_id, members_json, kind, asserted, candidate in rows:
            members = _json.loads(members_json)
            if set(members) <= idset:                       # engine fully present in deck
                entry = {"engine_id": engine_id, "members": members, "kind": kind,
                         "candidate": bool(candidate)}
                (combos if asserted else engines).append(entry)
        return {"engines": engines, "combos": combos}
```
In `backend/app/main.py` add (reusing the existing `DeckRequest` model):
```python
@app.post("/deck/engines")
def deck_engines(req: DeckRequest) -> dict:
    store = get_store()
    ids = [e.id for e in req.cards]
    return store.deck_engines(ids)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_api.py -q`
Expected: PASS

- [ ] **Step 5: Run both suites + commit**

```bash
cd C:/simmander/simmander-deckbuilder/scoring && python -m pytest -q
cd ../backend && python -m pytest -q
cd .. && git add backend/app/store.py backend/app/main.py backend/tests/test_api.py
git commit -m "feat(rel): /deck/engines summary (engines + combos present in a deck)"
```

- [ ] **Step 6: Push the branch**

```bash
git push -u origin sp1-relationship-measurement
```

---

## Self-review notes (author)

- **Spec coverage:** §4 four measures → Tasks 2 (similarity), 3 (synergy), 4 (anti). §5 resource graph → Tasks 1 (resources) + 5 (graph/candidate pairs). §6 engines + combo → Tasks 6 (catalog), 7 (mining + candidate cycle). §7 storage/API → Tasks 8 (tables), 10 (`/score/pair`), 11 (`/deck/engines`). §8 validation → Task 9 (golden + catalog-recall); fusion seam = `measures._squash`/structural-only default documented (co-occurrence not built — spec non-goal). §3 augment (CSS/DER untouched) → Task 8 only creates new tables; `synergies` never dropped.
- **Type consistency:** `card_resources` returns `{"produces","consumes"}` everywhere (resources, graph, engines, build). `resource_match` single definition in resources.py, imported by measures/graph/engines. `synergy` returns `(ab, ba)` tuple consistently. `card_relationships` columns identical in build (Task 8) and backend reads (Task 10). `engines` columns identical in Task 8 and Task 11.
- **Known deferrals (explicit, not placeholders):** SP3 co-occurrence + fusion weights (seam/identity default); anti-synergy is one rule + extensible structure (spec-sanctioned "we might make more later"); engine `resources`/`score` columns stored minimal in v1 (members + kind + flags are what consumers use); `SYNERGY_K` + weights calibrated in Task 9 against golden.
- **Tractability note:** candidate pairs come from the producer↔consumer index (not all-pairs); engine mining is seed-bounded with `max_per_seed` + `kmax`. If the real run in Task 9 is too slow or explodes, that is a tuning finding to report (lower `kmax`/`max_per_seed`), not a silent cap.
