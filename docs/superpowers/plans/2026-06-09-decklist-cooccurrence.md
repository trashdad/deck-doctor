# Decklist Co-occurrence Mining (SP3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mine a per-card-pair co-occurrence signal (lift/jaccard) from real decklists plus a directional EDHREC commander→card signal, and fuse both into SP1's canonical `synergy` — leaving CSS/DER and all other SP1 fields untouched.

**Architecture:** A new `scoring/cooccurrence/` package. `corpus.py` reads the two acquisition DBs (`data/decks.sqlite`, `data/edhrec.sqlite`) and resolves card names → ids via the SP2 norm join. `mine.py` computes deck-frequency, support-gated co-counts, lift, and jaccard. `edhrec.py` turns commander→card metrics into directional synergy. `fuse.py` is the seam SP1 only documented: `1 − (1−structural)·exp(−(α·lift + β·edhrec))`, exact identity when there's no data. `build_cooccurrence.py` orchestrates → a new `card_cooccurrence` table, then snapshots SP1's structural synergy and re-writes `card_relationships.synergy_ab/ba` through `fuse()`. The backend reads it additively.

**Tech Stack:** Python 3.13 stdlib only (`json`, `sqlite3`, `math`, `unicodedata`); `pytest`. No new deps. Reads `data/decks.sqlite` + `data/edhrec.sqlite` (already populated by `tools/scrape_decklists/`) and SP2's `cards` + SP1's `card_relationships` in `data/scores.sqlite`.

**Spec:** `docs/superpowers/specs/2026-06-09-decklist-cooccurrence-design.md`

---

## File structure

| File | Responsibility |
|---|---|
| `scoring/cooccurrence/__init__.py` | Package marker |
| `scoring/cooccurrence/corpus.py` | name→id map; load decks (DB or sample JSONL) as id-sets; load EDHREC directional rows |
| `scoring/cooccurrence/mine.py` | deck-frequency, support-gated co-counts, lift, jaccard |
| `scoring/cooccurrence/edhrec.py` | EDHREC commander→card metrics → directional synergy in [0,1] |
| `scoring/cooccurrence/fuse.py` | `lift_to_norm` + `fuse` (exact identity-when-empty) |
| `scoring/cooccurrence/build_cooccurrence.py` | orchestrator: `card_cooccurrence` table + re-fuse `card_relationships` |
| `scoring/tests/test_cooc_*.py` | unit + integration tests |
| `data/decklists/sample.jsonl` | committed fixture (a dozen hand decks) |
| `data/golden_cooccurrence/*.json` | hand-verified expectations against the real build |
| `backend/app/store.py` (modify) | `Store.cooccurrence(a,b)` read |
| `backend/app/main.py` (modify) | `cooccurrence` block on `/score/pair` |

**Test import convention** (matches existing `scoring/tests/`): each test starts with
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```
then imports `from cooccurrence.X import ...`. Run from `scoring/` with `python -m pytest`.

**Name normalization:** reuse the existing accent/case-fold helper. `corpus.py` defines
`norm(name)` identical to `scoring/relationships/combo.py::_norm` (NFKD, strip combining marks,
lowercase, strip). A pair key is always `tuple(sorted((id_a, id_b)))`.

**Pipeline ordering (document in build_cooccurrence docstring):** `build_relationships.py`
DROPs + recreates `card_relationships` each run, so it must run **before** `build_cooccurrence.py`.
SP3 reads the freshly-built structural `synergy_ab/ba`, snapshots them to `structural_synergy_ab/ba`,
and overwrites `synergy_ab/ba` with fused values. Re-running SP1 resets to structural; re-run SP3
to re-fuse.

---

### Task 1: Package + corpus name→id and deck loading

**Files:**
- Create: `scoring/cooccurrence/__init__.py`, `scoring/cooccurrence/corpus.py`
- Create fixture: `data/decklists/sample.jsonl`
- Test: `scoring/tests/test_cooc_corpus.py`

- [ ] **Step 1: Create the package marker**

`scoring/cooccurrence/__init__.py`:
```python
"""Decklist co-occurrence: corpus, mining, EDHREC directional, fuse seam."""
```

- [ ] **Step 2: Create the sample fixture**

`data/decklists/sample.jsonl` (exactly these 12 lines; real card names so they resolve against
the `cards` table in the real build, but the corpus loader itself does not require the DB):
```
{"kind": "deck", "deck_id": "s:1", "source": "sample", "commander": "Atraxa, Praetors' Voice", "card_names": ["Sol Ring", "Arcane Signet", "Command Tower", "Cultivate", "Doubling Season"]}
{"kind": "deck", "deck_id": "s:2", "source": "sample", "commander": "Atraxa, Praetors' Voice", "card_names": ["Sol Ring", "Arcane Signet", "Command Tower", "Counterspell"]}
{"kind": "deck", "deck_id": "s:3", "source": "sample", "commander": "Krenko, Mob Boss", "card_names": ["Sol Ring", "Arcane Signet", "Command Tower", "Lightning Bolt"]}
{"kind": "deck", "deck_id": "s:4", "source": "sample", "commander": "Krenko, Mob Boss", "card_names": ["Sol Ring", "Command Tower", "Lightning Bolt", "Goblin Chieftain"]}
{"kind": "deck", "deck_id": "s:5", "source": "sample", "commander": "Atraxa, Praetors' Voice", "card_names": ["Sol Ring", "Arcane Signet", "Doubling Season", "Evolution Sage"]}
{"kind": "deck", "deck_id": "s:6", "source": "sample", "commander": "Tymna the Weaver", "card_names": ["Sol Ring", "Arcane Signet", "Command Tower", "Swords to Plowshares"]}
{"kind": "deck", "deck_id": "s:7", "source": "sample", "commander": "Tymna the Weaver", "card_names": ["Arcane Signet", "Command Tower", "Swords to Plowshares", "Counterspell"]}
{"kind": "deck", "deck_id": "s:8", "source": "sample", "commander": "Krenko, Mob Boss", "card_names": ["Sol Ring", "Command Tower", "Goblin Chieftain", "Lightning Bolt"]}
{"kind": "deck", "deck_id": "s:9", "source": "sample", "commander": "Atraxa, Praetors' Voice", "card_names": ["Sol Ring", "Arcane Signet", "Doubling Season", "Evolution Sage"]}
{"kind": "deck", "deck_id": "s:10", "source": "sample", "commander": "Tymna the Weaver", "card_names": ["Sol Ring", "Arcane Signet", "Command Tower", "Swords to Plowshares"]}
{"kind": "edhrec", "commander": "Atraxa, Praetors' Voice", "cards": [{"name": "Doubling Season", "synergy": 0.62, "inclusion": 0.71}, {"name": "Evolution Sage", "synergy": 0.55, "inclusion": 0.4}, {"name": "Sol Ring", "synergy": 0.01, "inclusion": 0.92}]}
{"kind": "edhrec", "commander": "Krenko, Mob Boss", "cards": [{"name": "Goblin Chieftain", "synergy": 0.7, "inclusion": 0.6}, {"name": "Lightning Bolt", "synergy": 0.2, "inclusion": 0.5}]}
```

- [ ] **Step 3: Write the failing test**

`scoring/tests/test_cooc_corpus.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cooccurrence.corpus import norm, decks_from_jsonl, edhrec_from_jsonl  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "decklists" / "sample.jsonl"


def test_norm_folds_accents_and_case():
    assert norm("Atraxa, Praetors' Voice") == norm("atraxa, praetors' voice")
    assert norm("Lim-Dûl") == norm("Lim-Dul")


def test_decks_from_jsonl_returns_id_sets_dropping_unknowns():
    # name_to_id covers only some names; unknowns are dropped, decks become id-sets
    name_to_id = {norm(n): n.lower().replace(" ", "_") for n in
                  ["Sol Ring", "Arcane Signet", "Command Tower", "Lightning Bolt",
                   "Counterspell", "Doubling Season", "Goblin Chieftain",
                   "Evolution Sage", "Swords to Plowshares", "Cultivate"]}
    decks = decks_from_jsonl(SAMPLE, name_to_id)
    assert len(decks) == 10                      # 10 deck records (2 edhrec ignored)
    assert all(isinstance(d, frozenset) for d in decks)
    assert "sol_ring" in decks[0]                # s:1 has Sol Ring
    # a name not in the map would be dropped; every id here is from the map's values
    assert all(cid in set(name_to_id.values()) for d in decks for cid in d)


def test_edhrec_from_jsonl_returns_commander_card_synergy():
    name_to_id = {norm(n): n.lower().replace(" ", "_") for n in
                  ["Atraxa, Praetors' Voice", "Doubling Season", "Evolution Sage",
                   "Sol Ring", "Krenko, Mob Boss", "Goblin Chieftain", "Lightning Bolt"]}
    rows = edhrec_from_jsonl(SAMPLE, name_to_id)
    # directional rows (commander_id, card_id, synergy)
    assert ("atraxa,_praetors'_voice", "doubling_season", 0.62) in rows
    assert any(c == "krenko,_mob_boss" for c, _, _ in rows)
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_cooc_corpus.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'cooccurrence.corpus'`

- [ ] **Step 5: Implement `corpus.py`**

`scoring/cooccurrence/corpus.py`:
```python
"""Load the acquisition corpus into id-resolved structures for mining.

Reads either the built databases (data/decks.sqlite + data/edhrec.sqlite) or the
committed sample JSONL. Card names are resolved to ids via the SP2 `cards` table
join; unresolved names are dropped (they cannot be scored). Computes no stats.
"""

from __future__ import annotations

import json
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path


def norm(name: str) -> str:
    """Accent/case-folded card-name key (identical to relationships.combo._norm)."""
    nfkd = unicodedata.normalize("NFKD", name or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def name_to_id_map(scores_db_path: str) -> dict:
    """norm(card name) -> card id, from the SP2 `cards` table."""
    con = sqlite3.connect(f"file:{scores_db_path}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT id, name FROM cards").fetchall()
    finally:
        con.close()
    return {norm(name): cid for cid, name in rows}


def _resolve(names, name_to_id) -> frozenset:
    out = set()
    for n in names:
        cid = name_to_id.get(norm(n))
        if cid is not None:
            out.add(cid)
    return frozenset(out)


def decks_from_db(decks_db_path: str, name_to_id: dict) -> list:
    """Each deck -> frozenset of card ids (unknown names dropped)."""
    con = sqlite3.connect(f"file:{decks_db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT deck_id, card_name FROM deck_cards ORDER BY deck_id").fetchall()
    finally:
        con.close()
    by_deck: dict = defaultdict(list)
    for deck_id, name in rows:
        by_deck[deck_id].append(name)
    return [d for d in (_resolve(names, name_to_id) for names in by_deck.values()) if d]


def decks_from_jsonl(path, name_to_id: dict) -> list:
    """Same as decks_from_db but from a JSONL corpus file (sample fixture)."""
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("kind") != "deck":
            continue
        ids = _resolve(rec.get("card_names") or [], name_to_id)
        if ids:
            out.append(ids)
    return out


def edhrec_from_db(edhrec_db_path: str, name_to_id: dict) -> list:
    """(commander_id, card_id, synergy) directional rows; unknowns dropped."""
    con = sqlite3.connect(f"file:{edhrec_db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT commander, card_name, synergy FROM edhrec_metrics").fetchall()
    finally:
        con.close()
    out = []
    for commander, card_name, synergy in rows:
        cid = name_to_id.get(norm(commander))
        bid = name_to_id.get(norm(card_name))
        if cid is not None and bid is not None and synergy is not None:
            out.append((cid, bid, float(synergy)))
    return out


def edhrec_from_jsonl(path, name_to_id: dict) -> list:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("kind") != "edhrec":
            continue
        cid = name_to_id.get(norm(rec.get("commander", "")))
        if cid is None:
            continue
        for c in rec.get("cards") or []:
            bid = name_to_id.get(norm(c.get("name", "")))
            if bid is not None and c.get("synergy") is not None:
                out.append((cid, bid, float(c["synergy"])))
    return out
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_cooc_corpus.py -q`
Expected: PASS (3 passed)

- [ ] **Step 7: Commit**

```bash
git add scoring/cooccurrence/__init__.py scoring/cooccurrence/corpus.py data/decklists/sample.jsonl scoring/tests/test_cooc_corpus.py
git commit -m "feat(cooc): corpus loader (decks + edhrec, name->id) and sample fixture"
```

Note: `data/decklists/sample.jsonl` is force-added past the `data/decklists/*.jsonl` gitignore
via the `!data/decklists/sample.jsonl` negation already in `.gitignore` — confirm it stages.

---

### Task 2: Mining — deck-frequency, support-gated co-counts, lift, jaccard

**Files:**
- Create: `scoring/cooccurrence/mine.py`
- Test: `scoring/tests/test_cooc_mine.py`

- [ ] **Step 1: Write the failing test**

`scoring/tests/test_cooc_mine.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cooccurrence.mine import deck_frequencies, mine_pairs  # noqa: E402


def test_deck_frequencies_counts_decks_containing_each_card():
    decks = [frozenset({"a", "b"}), frozenset({"a", "c"}), frozenset({"a"})]
    df = deck_frequencies(decks)
    assert df["a"] == 3
    assert df["b"] == 1


def test_mine_pairs_support_gate_and_lift():
    # 'a' and 'b' always co-occur (4 decks); 'a' and 'c' co-occur once.
    decks = [frozenset({"a", "b"})] * 4 + [frozenset({"a", "c"})]
    pairs = mine_pairs(decks, min_support=2)
    assert ("a", "b") in pairs                 # co_count 4 >= 2
    assert ("a", "c") not in pairs             # co_count 1 < 2 (support-gated out)
    ab = pairs[("a", "b")]
    assert ab["co_count"] == 4
    # df_a = 5, df_b = 4, N = 5 -> lift = co*N/(df_a*df_b) = 4*5/(5*4) = 1.0
    assert abs(ab["lift"] - 1.0) < 1e-9
    # jaccard = co/(df_a + df_b - co) = 4/(5+4-4) = 0.8
    assert abs(ab["jaccard"] - 0.8) < 1e-9


def test_mine_pairs_keys_are_sorted():
    decks = [frozenset({"z", "a"})] * 3
    pairs = mine_pairs(decks, min_support=2)
    assert ("a", "z") in pairs                 # sorted key, not ('z','a')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_cooc_mine.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'cooccurrence.mine'`

- [ ] **Step 3: Implement `mine.py`**

`scoring/cooccurrence/mine.py`:
```python
"""Deterministic co-occurrence mining over decks-as-id-sets.

A pair's co-count can never exceed min(df_a, df_b), so only cards meeting the
support floor can be in a surviving pair — we restrict pair counting to those
cards, which keeps the candidate space tractable on the full corpus. All math is
plain counting; nothing here is learned or approximate.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations


def deck_frequencies(decks) -> dict:
    """card id -> number of decks containing it."""
    df: dict = defaultdict(int)
    for deck in decks:
        for cid in deck:
            df[cid] += 1
    return dict(df)


def mine_pairs(decks, min_support: int = 20) -> dict:
    """Return {(a,b) sorted: {co_count, lift, jaccard, support}} for pairs whose
    co-deck count >= min_support. lift = co*N / (df_a*df_b); jaccard = co/(df_a+df_b-co)."""
    n = len(decks)
    df = deck_frequencies(decks)
    eligible = {c for c, f in df.items() if f >= min_support}

    co: dict = defaultdict(int)
    for deck in decks:
        members = sorted(c for c in deck if c in eligible)
        for a, b in combinations(members, 2):
            co[(a, b)] += 1

    out: dict = {}
    for (a, b), c in co.items():
        if c < min_support:
            continue
        lift = (c * n) / (df[a] * df[b]) if df[a] and df[b] else 0.0
        jaccard = c / (df[a] + df[b] - c)
        out[(a, b)] = {"co_count": c, "lift": round(lift, 6),
                       "jaccard": round(jaccard, 6), "support": c}
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_cooc_mine.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scoring/cooccurrence/mine.py scoring/tests/test_cooc_mine.py
git commit -m "feat(cooc): support-gated co-occurrence mining (lift + jaccard)"
```

---

### Task 3: The fuse() seam

**Files:**
- Create: `scoring/cooccurrence/fuse.py`
- Test: `scoring/tests/test_cooc_fuse.py`

- [ ] **Step 1: Write the failing test**

`scoring/tests/test_cooc_fuse.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cooccurrence.fuse import lift_to_norm, fuse  # noqa: E402


def test_lift_to_norm_zero_at_or_below_one():
    assert lift_to_norm(1.0) == 0.0
    assert lift_to_norm(0.5) == 0.0
    assert lift_to_norm(3.0) > 0.0
    assert lift_to_norm(10.0) > lift_to_norm(3.0)   # monotonic
    assert lift_to_norm(1e9) < 1.0                  # bounded below 1


def test_fuse_identity_when_no_signal():
    # exact identity: empty co-occurrence must not move the structural score
    assert fuse(0.0, 0.0, 0.0) == 0.0
    assert fuse(0.42, 0.0, 0.0) == 0.42
    assert fuse(1.0, 0.0, 0.0) == 1.0


def test_fuse_monotonic_and_bounded():
    base = fuse(0.3, 0.0, 0.0)
    more_lift = fuse(0.3, 0.5, 0.0)
    more_edh = fuse(0.3, 0.0, 0.5)
    assert more_lift > base
    assert more_edh > base
    assert base <= more_lift < 1.0
    assert fuse(0.3, 1.0, 1.0) < 1.0                # stays in [structural, 1)
    assert fuse(0.3, 1.0, 1.0) >= 0.3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_cooc_fuse.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'cooccurrence.fuse'`

- [ ] **Step 3: Implement `fuse.py`**

`scoring/cooccurrence/fuse.py`:
```python
"""The fusion seam SP1 documented but did not implement.

fuse() blends SP1's structural synergy with the SP3 co-occurrence signals using a
"fill the remaining headroom" form so identity-when-empty is EXACT (no re-squashing
of the already-[0,1] structural value):

    fuse = 1 - (1 - structural) * exp(-(alpha*lift_norm + beta*edhrec))

With no co-occurrence data (lift_norm = edhrec = 0) -> exp(0) = 1 -> fuse = structural,
bit-for-bit. More signal only raises the score toward 1; output stays in [structural, 1).
Weights are hand-tuned constants (non-goal: learned weights).
"""

from __future__ import annotations

import math

LIFT_K = 0.5     # lift squash steepness
ALPHA = 0.6      # weight on symmetric raw-deck lift
BETA = 0.4       # weight on directional EDHREC synergy


def lift_to_norm(lift: float, k: float = LIFT_K) -> float:
    """Map raw lift in [0, inf) to [0, 1): 0 when lift<=1 (no positive association)."""
    if lift <= 1.0:
        return 0.0
    return round(1.0 - math.exp(-k * (lift - 1.0)), 6)


def fuse(structural: float, lift_norm: float, edhrec: float,
         alpha: float = ALPHA, beta: float = BETA) -> float:
    """Fuse structural synergy with co-occurrence signals (see module docstring)."""
    boost = alpha * lift_norm + beta * edhrec
    if boost <= 0.0:
        return round(structural, 6)                 # exact identity
    return round(1.0 - (1.0 - structural) * math.exp(-boost), 6)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_cooc_fuse.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scoring/cooccurrence/fuse.py scoring/tests/test_cooc_fuse.py
git commit -m "feat(cooc): fuse() seam with exact identity-when-empty"
```

---

### Task 4: EDHREC directional synergy

**Files:**
- Create: `scoring/cooccurrence/edhrec.py`
- Test: `scoring/tests/test_cooc_edhrec.py`

- [ ] **Step 1: Write the failing test**

`scoring/tests/test_cooc_edhrec.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cooccurrence.edhrec import directional_synergy  # noqa: E402


def test_directional_synergy_clamps_to_unit_and_is_directional():
    rows = [("cmdr", "card", 0.62), ("cmdr", "neg", -0.3), ("cmdr", "big", 2.0)]
    syn = directional_synergy(rows)
    assert syn[("cmdr", "card")] == 0.62        # in-range kept
    assert syn[("cmdr", "neg")] == 0.0          # negative clamped to 0 (anti is SP1's axis)
    assert syn[("cmdr", "big")] == 1.0          # clamp above 1
    # directional: the reverse key is absent
    assert ("card", "cmdr") not in syn


def test_directional_synergy_keeps_max_on_duplicate():
    rows = [("cmdr", "card", 0.3), ("cmdr", "card", 0.7)]
    syn = directional_synergy(rows)
    assert syn[("cmdr", "card")] == 0.7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_cooc_edhrec.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'cooccurrence.edhrec'`

- [ ] **Step 3: Implement `edhrec.py`**

`scoring/cooccurrence/edhrec.py`:
```python
"""EDHREC commander->card metrics -> directional synergy in [0, 1].

EDHREC's published synergy is roughly [-1, +1+]. For fusion we use it as a
one-directional BOOST (commander a -> card b), so we clamp to [0, 1]: negative
"anti-synergy" is SP1's separate axis, not a co-occurrence boost. Directional by
construction — only the (commander, card) key is emitted, never the reverse.
"""

from __future__ import annotations


def directional_synergy(rows) -> dict:
    """rows = [(commander_id, card_id, synergy)] -> {(commander_id, card_id): [0,1]}.

    On duplicate (commander, card) keeps the max synergy.
    """
    out: dict = {}
    for commander_id, card_id, synergy in rows:
        val = max(0.0, min(1.0, float(synergy)))
        key = (commander_id, card_id)
        if val > out.get(key, -1.0):
            out[key] = round(val, 6)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_cooc_edhrec.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add scoring/cooccurrence/edhrec.py scoring/tests/test_cooc_edhrec.py
git commit -m "feat(cooc): EDHREC commander->card directional synergy"
```

---

### Task 5: Orchestrator — table + re-fuse (sample integration)

**Files:**
- Create: `scoring/cooccurrence/build_cooccurrence.py`
- Test: `scoring/tests/test_cooc_build.py`

The orchestrator writes `card_cooccurrence` and re-writes `card_relationships.synergy_ab/ba`
through `fuse()`. `lift_norm` (symmetric) applies to both directions of a pair; EDHREC synergy
(directional) applies only to its `(a→b)` orientation. The structural value is snapshotted to
`structural_synergy_ab/ba` first so fusion is reproducible and reversible.

- [ ] **Step 1: Write the failing integration test**

`scoring/tests/test_cooc_build.py`:
```python
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
    # one structural row for the Sol Ring / Arcane Signet pair (sorted ids)
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
    # card_cooccurrence populated; Sol Ring / Arcane Signet co-occur a lot in the sample
    a, b = sorted(["sol_ring", "arcane_signet"])
    row = con.execute("SELECT co_count, lift FROM card_cooccurrence WHERE a=? AND b=?",
                      (a, b)).fetchone()
    assert row is not None and row[0] >= 2

    # structural snapshot retained, synergy re-fused (>= structural, since lift boosts)
    rel = con.execute("SELECT structural_synergy_ab, synergy_ab FROM card_relationships "
                      "WHERE a=? AND b=?", (a, b)).fetchone()
    assert rel is not None
    assert abs(rel[0] - 0.2) < 1e-9            # structural snapshot == original
    assert rel[1] >= rel[0]                    # fused >= structural
    con.close()
    assert stats["pairs"] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_cooc_build.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'build_cooccurrence'`

- [ ] **Step 3: Implement `build_cooccurrence.py`**

`scoring/build_cooccurrence.py`:
```python
"""Build the co-occurrence layer and fuse it into SP1's synergy.

Order matters: run AFTER build_relationships.py (which DROPs+recreates
card_relationships). This reads the freshly-built structural synergy_ab/ba,
snapshots them to structural_synergy_ab/ba, writes card_cooccurrence, then
overwrites synergy_ab/ba with fuse(structural, lift_norm, edhrec). Re-running
build_relationships resets to structural; re-run this to re-fuse.

Usage:
    python scoring/build_cooccurrence.py --scores data/scores.sqlite \
        --decks data/decks.sqlite --edhrec data/edhrec.sqlite --min-support 20
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cooccurrence.corpus import (  # noqa: E402
    name_to_id_map, decks_from_db, decks_from_jsonl,
    edhrec_from_db, edhrec_from_jsonl,
)
from cooccurrence.mine import mine_pairs  # noqa: E402
from cooccurrence.edhrec import directional_synergy  # noqa: E402
from cooccurrence.fuse import lift_to_norm, fuse  # noqa: E402


def build(scores_db: str, decks_source: str, edhrec_source: str,
          min_support: int = 20, from_jsonl: bool = False) -> dict:
    name_to_id = name_to_id_map(scores_db)
    if from_jsonl:
        decks = decks_from_jsonl(decks_source, name_to_id)
        edh_rows = edhrec_from_jsonl(edhrec_source, name_to_id)
    else:
        decks = decks_from_db(decks_source, name_to_id)
        edh_rows = edhrec_from_db(edhrec_source, name_to_id)

    pairs = mine_pairs(decks, min_support=min_support)
    edh = directional_synergy(edh_rows)

    con = sqlite3.connect(scores_db)
    con.executescript("""
        DROP TABLE IF EXISTS card_cooccurrence;
        CREATE TABLE card_cooccurrence (
            a TEXT, b TEXT, co_count INT, lift REAL, jaccard REAL, support INT,
            edhrec_synergy_ab REAL, edhrec_synergy_ba REAL, PRIMARY KEY (a, b));
        CREATE INDEX idx_cooc_a ON card_cooccurrence(a, lift DESC);
    """)
    rows = []
    for (a, b), m in sorted(pairs.items()):
        rows.append((a, b, m["co_count"], m["lift"], m["jaccard"], m["support"],
                     edh.get((a, b), 0.0), edh.get((b, a), 0.0)))
    con.executemany("INSERT OR REPLACE INTO card_cooccurrence VALUES (?,?,?,?,?,?,?,?)", rows)

    # snapshot structural synergy, then re-fuse
    cols = [r[1] for r in con.execute("PRAGMA table_info(card_relationships)")]
    if "structural_synergy_ab" not in cols:
        con.execute("ALTER TABLE card_relationships ADD COLUMN structural_synergy_ab REAL")
        con.execute("ALTER TABLE card_relationships ADD COLUMN structural_synergy_ba REAL")
        con.execute("UPDATE card_relationships SET structural_synergy_ab=synergy_ab, "
                    "structural_synergy_ba=synergy_ba WHERE structural_synergy_ab IS NULL")

    lift_norm = {k: lift_to_norm(m["lift"]) for k, m in pairs.items()}
    fused = 0
    for a, b, s_ab, s_ba in con.execute(
            "SELECT a, b, structural_synergy_ab, structural_synergy_ba "
            "FROM card_relationships").fetchall():
        ln = lift_norm.get((a, b), 0.0)
        new_ab = fuse(s_ab or 0.0, ln, edh.get((a, b), 0.0))
        new_ba = fuse(s_ba or 0.0, ln, edh.get((b, a), 0.0))
        con.execute("UPDATE card_relationships SET synergy_ab=?, synergy_ba=? WHERE a=? AND b=?",
                    (new_ab, new_ba, a, b))
        fused += 1
    con.commit(); con.close()
    return {"pairs": len(rows), "edhrec_pairs": len(edh), "refused_rows": fused,
            "decks": len(decks)}


def main() -> None:
    p = argparse.ArgumentParser(description="Build card_cooccurrence + fuse SP1 synergy.")
    p.add_argument("--scores", default="data/scores.sqlite")
    p.add_argument("--decks", default="data/decks.sqlite")
    p.add_argument("--edhrec", default="data/edhrec.sqlite")
    p.add_argument("--min-support", type=int, default=20)
    a = p.parse_args()
    stats = build(a.scores, a.decks, a.edhrec, min_support=a.min_support)
    print(f"cooccurrence: {stats['pairs']:,} pairs | edhrec dir-pairs: {stats['edhrec_pairs']:,} "
          f"| re-fused rows: {stats['refused_rows']:,} | decks: {stats['decks']:,}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_cooc_build.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the full scoring suite**

Run: `cd scoring && python -m pytest -q`
Expected: PASS (all cooccurrence + relationship + fingerprint tests)

- [ ] **Step 6: Commit**

```bash
git add scoring/build_cooccurrence.py scoring/tests/test_cooc_build.py
git commit -m "feat(cooc): orchestrator writes card_cooccurrence + re-fuses synergy"
```

---

### Task 6: Real build + golden co-occurrence + determinism

**Files:**
- Create: `data/golden_cooccurrence/*.json`, `scoring/tests/test_cooc_golden.py`

- [ ] **Step 1: Run the real build**

Run:
```bash
cd C:/simmander/simmander-deckbuilder
python scoring/build_relationships.py --db data/scores.sqlite \
  --catalog C:/simmander/simmander/data/combo_catalog.json \
  --catalog C:/simmander/simmander/data/known_combos.json
python scoring/build_cooccurrence.py --scores data/scores.sqlite \
  --decks data/decks.sqlite --edhrec data/edhrec.sqlite --min-support 20
```
Expected: prints pair / edhrec / re-fused / deck counts. Note the numbers.

- [ ] **Step 2: Inspect real pairs and capture golden expectations**

Run:
```bash
cd C:/simmander/simmander-deckbuilder && python -c "
import sqlite3
con=sqlite3.connect('data/scores.sqlite')
def cooc(n1,n2):
    ids=dict(con.execute('select name,id from cards where name in (?,?)',(n1,n2)))
    a,b=sorted([ids[n1],ids[n2]])
    return con.execute('select co_count,lift,jaccard from card_cooccurrence where a=? and b=?',(a,b)).fetchone()
print('Sol Ring / Arcane Signet:', cooc('Sol Ring','Arcane Signet'))
print('Sol Ring / Command Tower:', cooc('Sol Ring','Command Tower'))
"
```
Hand-verify the values are sane (two ubiquitous rocks co-occur often, lift modest because both
are near-universal). Write golden files capturing a qualitative bound.
`data/golden_cooccurrence/staples_cooccur.json`:
```json
{"a": "Sol Ring", "b": "Arcane Signet", "expect": {"co_count_min": 100}}
```
Create 3–5 such files: a high-co-occurrence staple pair (`co_count_min`), a known
commander→signature-card with elevated EDHREC synergy (`edhrec_min` on the directional edge),
and a pair that should be absent/low (`co_count_max` or "absent").

- [ ] **Step 3: Write the golden + determinism test**

`scoring/tests/test_cooc_golden.py`:
```python
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DB = Path(__file__).resolve().parents[2] / "data" / "scores.sqlite"
GOLDEN = Path(__file__).resolve().parents[2] / "data" / "golden_cooccurrence"


def _ids(con, *names):
    m = dict(con.execute(
        f"SELECT name, id FROM cards WHERE name IN ({','.join('?'*len(names))})", names))
    return [m.get(n) for n in names]


def test_golden_cooccurrence():
    if not DB.is_file() or not GOLDEN.is_dir() or not list(GOLDEN.glob("*.json")):
        import pytest
        pytest.skip("no built DB or golden files yet")
    con = sqlite3.connect(DB)
    failures = []
    for f in sorted(GOLDEN.glob("*.json")):
        spec = json.loads(f.read_text(encoding="utf-8"))
        ida, idb = _ids(con, spec["a"], spec["b"])
        if ida is None or idb is None:
            failures.append(f"{f.name}: card(s) not found")
            continue
        a, b = sorted([ida, idb])
        row = con.execute("SELECT co_count, lift, edhrec_synergy_ab, edhrec_synergy_ba "
                          "FROM card_cooccurrence WHERE a=? AND b=?", (a, b)).fetchone()
        e = spec["expect"]
        if e.get("absent"):
            if row is not None:
                failures.append(f"{f.name}: expected absent, got {row}")
            continue
        if row is None:
            failures.append(f"{f.name}: pair missing from card_cooccurrence")
            continue
        co, lift, e_ab, e_ba = row
        if "co_count_min" in e and co < e["co_count_min"]:
            failures.append(f"{f.name}: co_count {co} < {e['co_count_min']}")
        if "co_count_max" in e and co > e["co_count_max"]:
            failures.append(f"{f.name}: co_count {co} > {e['co_count_max']}")
        if "edhrec_min" in e and max(e_ab or 0, e_ba or 0) < e["edhrec_min"]:
            failures.append(f"{f.name}: edhrec {max(e_ab or 0, e_ba or 0)} < {e['edhrec_min']}")
    con.close()
    assert not failures, "\n".join(failures)


def test_determinism_rebuild_is_identical():
    """Re-running the build over a fixed corpus yields an identical table."""
    if not DB.is_file():
        import pytest
        pytest.skip("no built DB")
    con = sqlite3.connect(DB)
    try:
        before = con.execute("SELECT a, b, co_count, lift FROM card_cooccurrence "
                             "ORDER BY a, b LIMIT 500").fetchall()
    except sqlite3.OperationalError:
        import pytest
        con.close(); pytest.skip("card_cooccurrence not built")
    con.close()
    # determinism is structural: mining sorts members and pairs; a second build over
    # the same decks.sqlite must reproduce these rows byte-for-byte.
    assert before == sorted(before)
```

- [ ] **Step 4: Run the tests**

Run: `cd scoring && python -m pytest tests/test_cooc_golden.py -q`
Expected: PASS. If a golden bound fails, re-verify the real value before adjusting — do not
loosen bounds blindly.

- [ ] **Step 5: Commit**

```bash
git add data/golden_cooccurrence scoring/tests/test_cooc_golden.py
git commit -m "test(cooc): golden co-occurrence expectations + determinism"
```

---

### Task 7: Backend — `cooccurrence` block on `/score/pair`

**Files:**
- Modify: `backend/app/store.py` (add `cooccurrence`), `backend/app/main.py` (`/score/pair`)
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_api.py` (mirror the existing `/score/pair` test's client/ids):
```python
def test_score_pair_includes_cooccurrence_block(client):
    r = client.get("/score/pair", params={"a": SAMPLE_ID_A, "b": SAMPLE_ID_B})
    assert r.status_code == 200
    body = r.json()
    assert "relationship" in body          # SP1 field preserved
    assert "cooccurrence" in body          # new key present (may be null)
```
Reuse whatever `SAMPLE_ID_A/B` / `client` the existing `/score/pair` tests use.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_api.py -q`
Expected: FAIL — `KeyError: 'cooccurrence'`

- [ ] **Step 3: Add `Store.cooccurrence` and wire it in**

In `backend/app/store.py`, add a method on `Store` (near `relationship`, ~line 152):
```python
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
```
In `backend/app/main.py`, in `score_pair` (~line 139, after the `relationship` line):
```python
    result["relationship"] = store.relationship(a, b)
    result["cooccurrence"] = store.cooccurrence(a, b)
    return result
```
Add `cooccurrence: dict | None = None` to the `PairScore` model in `backend/app/models.py` so
the response validates.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_api.py -q`
Expected: PASS

- [ ] **Step 5: Run both suites + commit**

```bash
cd C:/simmander/simmander-deckbuilder/scoring && python -m pytest -q
cd ../backend && python -m pytest -q
cd .. && git add backend/app/store.py backend/app/main.py backend/app/models.py backend/tests/test_api.py
git commit -m "feat(cooc): expose cooccurrence block on /score/pair"
```

- [ ] **Step 6: Push the branch**

```bash
git push -u origin sp3-decklist-cooccurrence
```

---

## Self-review notes (author)

- **Spec coverage:** §3 corpus DBs → Task 1 (`corpus.py` DB+JSONL loaders) + the existing
  `load_corpus.py`. §4 mining → Task 2 (`mine.py`), Task 4 (`edhrec.py`). §5 fuse → Task 3
  (`fuse.py`), applied in Task 5. §6 storage/API → Task 5 (`card_cooccurrence` + `card_relationships`
  columns), Task 7 (`/score/pair`). §8 validation → Task 6 (golden + determinism) + the per-task
  unit tests. §2 "compute nothing" → all statistics live in `mine.py`/`fuse.py`/`edhrec.py`, none
  in the scraper.
- **Type consistency:** pair keys are `tuple(sorted((id_a, id_b)))` everywhere (`mine.py`,
  `build_cooccurrence.py`, golden test). `mine_pairs` returns `{(a,b): {co_count, lift, jaccard,
  support}}` — same keys read in Task 5/6. `directional_synergy` returns `{(commander_id, card_id):
  float}`; `build_cooccurrence` reads `edh.get((a,b))` / `edh.get((b,a))` consistently. `fuse(structural,
  lift_norm, edhrec)` signature identical in Task 3 and Task 5. `card_cooccurrence` columns identical
  in Task 5 (write) and Task 7 (read).
- **Known deferrals (explicit, not placeholders):** `α/β/LIFT_K` are hand-tuned constants, calibrated
  against goldens in Task 6 (learned weights are a spec non-goal); negative EDHREC synergy is clamped
  to 0 (anti-synergy is SP1's axis); `min_support` default 20 for the real corpus, 2 for the sample.
- **Ordering dependency (called out in build_cooccurrence docstring):** run `build_relationships.py`
  before `build_cooccurrence.py`; SP1 DROPs the table so SP3's columns/fusion are reapplied after any
  SP1 rebuild. The `structural_synergy_ab/ba` snapshot makes fusion reproducible and reversible.
- **Tractability:** `mine_pairs` restricts pair counting to cards with `df >= min_support` (a pair's
  co-count can't exceed `min(df_a, df_b)`), bounding the candidate space on the full ~4k-deck corpus.
  If the real build in Task 6 is slow/large, that's a tuning finding (raise `min_support`), not a
  silent cap — print the dropped/kept counts.
