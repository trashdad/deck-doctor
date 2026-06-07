# Card Fingerprint (SP2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, near-lossless structured behavioral *fingerprint* for every Commander-legal card from simmander's MTGish typed corpus (no LLM), with auto-derived views (flat tags / inverted index / feature-vector seam) and a QA harness (golden regression + coverage + unmapped-operator reports).

**Architecture:** A new `scoring/fingerprints/` package. `project.py` walks each card's MTGish `Rules` tree into per-ability structured records (`schema.py` dataclasses), preserving the raw subtree. `derive.py` turns records into the flat tags / inverted index / vector the UI and SP1 consume. `qa.py` enforces correctness. `build_fingerprints.py` orchestrates project → persist (SQLite) → derive → QA. The canonical `verb` is the raw MTGish `_Action` operator string; curated tag naming lives only in `derive.py`, so the canonical stays lossless and the unmapped-operator report tracks naming gaps for free.

**Tech Stack:** Python 3.13 stdlib only (`json`, `sqlite3`, `dataclasses`, `unicodedata`); `pytest` for tests. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-07-card-fingerprint-design.md`

---

## File structure

| File | Responsibility |
|---|---|
| `scoring/fingerprints/__init__.py` | Package marker |
| `scoring/fingerprints/schema.py` | `Amount`, `Effect`, `AbilityRecord` dataclasses + JSON (de)serialization |
| `scoring/fingerprints/project.py` | MTGish `Rules` tree → `list[AbilityRecord]` (the projector) |
| `scoring/fingerprints/derive.py` | `AbilityRecord` → flat tags (new namespaces), inverted index, feature vector |
| `scoring/fingerprints/qa.py` | golden regression, coverage report, unmapped-operator report |
| `scoring/build_fingerprints.py` | CLI orchestrator: project → persist → derive → QA |
| `scoring/prep_cards.py` (modify) | exclude acorn / Un-set cards from the corpus |
| `scoring/tests/test_fp_schema.py` | schema round-trip tests |
| `scoring/tests/test_fp_project.py` | projector tests (real MTGish fixtures) |
| `scoring/tests/test_fp_derive.py` | derive-layer tests |
| `scoring/tests/test_fp_qa.py` | QA-harness tests |
| `scoring/tests/test_prep_cards.py` | acorn-exclusion test |
| `data/golden/*.json` | hand-verified canonical records (regression fixtures) |
| `data/outliers/*.json` | hand-coded records for genuine MTGish misses |

**Test import convention** (matches `scoring/tests/test_evaluate.py`): each test file starts with
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```
then imports `from fingerprints.schema import ...`. Run all tests from `scoring/` with `python -m pytest`.

---

### Task 1: Package + schema dataclasses

**Files:**
- Create: `scoring/fingerprints/__init__.py`
- Create: `scoring/fingerprints/schema.py`
- Test: `scoring/tests/test_fp_schema.py`

- [ ] **Step 1: Create the package marker**

Create `scoring/fingerprints/__init__.py`:
```python
"""Structured card fingerprint: schema, projector, derived views, QA."""
```

- [ ] **Step 2: Write the failing schema test**

Create `scoring/tests/test_fp_schema.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fingerprints.schema import Amount, Effect, AbilityRecord  # noqa: E402


def test_amount_literal_roundtrip():
    a = Amount(kind="literal", value=13)
    assert Amount.from_dict(a.to_dict()) == a
    assert a.to_dict()["kind"] == "literal"


def test_amount_dynamic_roundtrip():
    a = Amount(kind="dynamic", count={"counted_object": "creature", "zone": "battlefield"})
    d = a.to_dict()
    assert d["count"]["counted_object"] == "creature"
    assert Amount.from_dict(d) == a


def test_ability_record_roundtrip():
    rec = AbilityRecord(
        ability_idx=0,
        kind="spell",
        effects=[Effect(verb="SpellDealsDamage", object="creature",
                        scope="EachPermanent", quantifier="each",
                        targeted=False, amount=Amount(kind="literal", value=13))],
        raw={"_Rule": "SpellActions"},
    )
    back = AbilityRecord.from_dict(rec.to_dict())
    assert back == rec
    assert back.effects[0].amount.value == 13
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_fp_schema.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fingerprints.schema'`

- [ ] **Step 4: Implement the schema**

Create `scoring/fingerprints/schema.py`:
```python
"""Dataclasses for the structured card fingerprint.

A card -> list[AbilityRecord]. Each ability -> Effects. Amounts are composable
(literal | x | dynamic) per the Forge Count$ / XMage DynamicValue prior art.
All dataclasses are JSON-round-trippable so they persist as a single `record`
column and reload identically (golden-regression depends on exact equality).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# Allowed ability kinds (CR-flavoured; extended for replacement/prevention/restriction).
KINDS = ("triggered", "activated", "static", "spell",
         "replacement", "prevention", "restriction")


@dataclass
class Amount:
    kind: str = "literal"                 # "literal" | "x" | "dynamic"
    value: Optional[int] = None           # set when kind == "literal"
    count: Optional[dict] = None          # set when kind == "dynamic"

    def to_dict(self) -> dict:
        return {"kind": self.kind, "value": self.value, "count": self.count}

    @classmethod
    def from_dict(cls, d: dict) -> "Amount":
        return cls(kind=d.get("kind", "literal"),
                   value=d.get("value"), count=d.get("count"))


@dataclass
class Effect:
    verb: str                              # raw MTGish _Action op (lossless)
    object: Optional[str] = None           # affected object TYPE (e.g. "creature")
    prefixes: list[str] = field(default_factory=list)   # other/another/target/each
    scope: Optional[str] = None            # who/what affected (recipient/player token)
    quantifier: Optional[str] = None       # all | each | single | up_to | n
    targeted: bool = False                 # targets vs affects-without-targeting
    amount: Optional[Amount] = None
    duration: Optional[str] = None
    grants: Optional[str] = None           # keyword granted (innate-vs-granted)
    sub_effects: list["Effect"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "verb": self.verb, "object": self.object, "prefixes": self.prefixes,
            "scope": self.scope, "quantifier": self.quantifier,
            "targeted": self.targeted,
            "amount": self.amount.to_dict() if self.amount else None,
            "duration": self.duration, "grants": self.grants,
            "sub_effects": [e.to_dict() for e in self.sub_effects],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Effect":
        return cls(
            verb=d["verb"], object=d.get("object"),
            prefixes=list(d.get("prefixes") or []),
            scope=d.get("scope"), quantifier=d.get("quantifier"),
            targeted=bool(d.get("targeted", False)),
            amount=Amount.from_dict(d["amount"]) if d.get("amount") else None,
            duration=d.get("duration"), grants=d.get("grants"),
            sub_effects=[cls.from_dict(x) for x in (d.get("sub_effects") or [])],
        )


@dataclass
class AbilityRecord:
    ability_idx: int
    kind: str = "static"
    trigger: Optional[dict] = None
    cost: Optional[dict] = None
    timing: Optional[str] = None
    condition: Optional[dict] = None
    optional: bool = False
    modal: Optional[dict] = None
    effects: list[Effect] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ability_idx": self.ability_idx, "kind": self.kind,
            "trigger": self.trigger, "cost": self.cost, "timing": self.timing,
            "condition": self.condition, "optional": self.optional,
            "modal": self.modal,
            "effects": [e.to_dict() for e in self.effects],
            "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AbilityRecord":
        return cls(
            ability_idx=d["ability_idx"], kind=d.get("kind", "static"),
            trigger=d.get("trigger"), cost=d.get("cost"), timing=d.get("timing"),
            condition=d.get("condition"), optional=bool(d.get("optional", False)),
            modal=d.get("modal"),
            effects=[Effect.from_dict(x) for x in (d.get("effects") or [])],
            raw=d.get("raw") or {},
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_fp_schema.py -q`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add scoring/fingerprints/__init__.py scoring/fingerprints/schema.py scoring/tests/test_fp_schema.py
git commit -m "feat(fp): add fingerprint schema dataclasses with JSON round-trip"
```

---

### Task 2: Amount extraction (`_GameNumber`)

**Files:**
- Create: `scoring/fingerprints/project.py` (start it)
- Test: `scoring/tests/test_fp_project.py`

MTGish amount shapes (real): literal = `{"_GameNumber": "Integer", "args": 13}`; dynamic =
`{"_GameNumber": "TheNumberOfPermanentsOnTheBattlefield", "args": {"_Permanents": "IsCardtype", "args": "Creature"}}`.

- [ ] **Step 1: Write the failing test**

Create `scoring/tests/test_fp_project.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fingerprints.project import parse_amount  # noqa: E402


def test_parse_amount_literal():
    node = {"_GameNumber": "Integer", "args": 13}
    a = parse_amount(node)
    assert a.kind == "literal" and a.value == 13


def test_parse_amount_dynamic():
    node = {"_GameNumber": "TheNumberOfPermanentsOnTheBattlefield",
            "args": {"_Permanents": "IsCardtype", "args": "Creature"}}
    a = parse_amount(node)
    assert a.kind == "dynamic"
    assert a.count["op"] == "TheNumberOfPermanentsOnTheBattlefield"
    assert a.count["counted_object"] == "Creature"


def test_parse_amount_none():
    assert parse_amount(None) is None
    assert parse_amount({"no_game_number": 1}) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_fp_project.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fingerprints.project'`

- [ ] **Step 3: Implement `parse_amount`**

Create `scoring/fingerprints/project.py`:
```python
"""Project MTGish typed `Rules` trees into structured AbilityRecords.

Canonical `verb` is the raw MTGish `_Action` operator string (lossless); curated
naming is the derive layer's job. The projector handles the structural skeleton
(rule kind, cost, trigger, action lists, control-flow wrappers, amounts, scope,
targeting) and leaves unknown leaf ops as raw verbs (surfaced by the QA
unmapped-operator report).
"""

from __future__ import annotations

from typing import Any, Optional

from .schema import Amount, Effect, AbilityRecord


def parse_amount(node: Any) -> Optional[Amount]:
    """Turn a `_GameNumber` node into an Amount, or None if there isn't one."""
    if not isinstance(node, dict) or "_GameNumber" not in node:
        return None
    op = node["_GameNumber"]
    args = node.get("args")
    if op == "Integer":
        return Amount(kind="literal", value=args if isinstance(args, int) else None)
    # Anything else is a dynamic count; capture what it counts when discoverable.
    counted = None
    if isinstance(args, dict) and "_Permanents" in args:
        counted = args.get("args") if isinstance(args.get("args"), str) else None
    return Amount(kind="dynamic", count={"op": op, "counted_object": counted, "raw": args})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_fp_project.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scoring/fingerprints/project.py scoring/tests/test_fp_project.py
git commit -m "feat(fp): parse MTGish _GameNumber into literal/dynamic Amount"
```

---

### Task 3: Scope, quantifier & targeting helpers

**Files:**
- Modify: `scoring/fingerprints/project.py`
- Test: `scoring/tests/test_fp_project.py`

Real shapes: recipient `{"_DamageRecipient": "EachPermanent", "args": {"_Permanents": "IsCardtype", "args": "Creature"}}`; single `{"_Permanents": "SinglePermanent", ...}`; player `{"_Players": "Opponent"}` / `{"_Player": "You"}`.

- [ ] **Step 1: Write the failing test (append to `test_fp_project.py`)**

```python
from fingerprints.project import parse_scope  # noqa: E402


def test_scope_each_permanent():
    node = {"_DamageRecipient": "EachPermanent",
            "args": {"_Permanents": "IsCardtype", "args": "Creature"}}
    sc = parse_scope(node)
    assert sc["scope"] == "EachPermanent"
    assert sc["object"] == "Creature"
    assert sc["quantifier"] == "each"


def test_scope_single_permanent():
    node = {"_Permanents": "SinglePermanent", "args": {"_Permanent": "ThisPermanent"}}
    assert parse_scope(node)["quantifier"] == "single"


def test_scope_player_opponent():
    node = {"_Players": "Opponent"}
    sc = parse_scope(node)
    assert sc["scope"] == "Opponent" and sc["object"] == "player"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_fp_project.py -q`
Expected: FAIL — `ImportError: cannot import name 'parse_scope'`

- [ ] **Step 3: Implement `parse_scope`**

Append to `scoring/fingerprints/project.py`:
```python
# Map MTGish quantifier-bearing tokens -> our quantifier axis.
_QUANTIFIER = {
    "EachPermanent": "each", "AllPermanents": "all", "SinglePermanent": "single",
    "EachPlayer": "each", "AllPlayers": "all", "AllOpponents": "all",
    "EachOpponent": "each", "SinglePlayer": "single", "SingleOpponent": "single",
}


def parse_scope(node: Any) -> dict:
    """Extract {scope, object, quantifier} from a recipient/players/permanents node.

    Returns empty-ish dict fields (None) when a part is absent.
    """
    out = {"scope": None, "object": None, "quantifier": None}
    if not isinstance(node, dict):
        return out

    # Recipient wrappers carry the scope token in their value.
    for wrapper in ("_DamageRecipient", "_Players", "_Player", "_Permanents", "_Permanent"):
        if wrapper in node:
            token = node[wrapper]
            out["scope"] = token
            out["quantifier"] = _QUANTIFIER.get(token)
            if wrapper in ("_Players", "_Player"):
                out["object"] = "player"
            break

    # Object type lives in a nested _Permanents: IsCardtype somewhere in args.
    obj = _find_cardtype(node)
    if obj:
        out["object"] = obj
    return out


def _find_cardtype(node: Any, depth: int = 0) -> Optional[str]:
    """Find the first `_Permanents: IsCardtype` cardtype string under a node."""
    if depth > 8 or not isinstance(node, (dict, list)):
        return None
    if isinstance(node, dict):
        if node.get("_Permanents") == "IsCardtype" and isinstance(node.get("args"), str):
            return node["args"]
        for v in node.values():
            r = _find_cardtype(v, depth + 1)
            if r:
                return r
    else:
        for v in node:
            r = _find_cardtype(v, depth + 1)
            if r:
                return r
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_fp_project.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add scoring/fingerprints/project.py scoring/tests/test_fp_project.py
git commit -m "feat(fp): extract scope/object/quantifier from MTGish nodes"
```

---

### Task 4: Effect extraction + control-flow recursion

**Files:**
- Modify: `scoring/fingerprints/project.py`
- Test: `scoring/tests/test_fp_project.py`

Walk an *action list*, producing `Effect`s. Handle the structural wrappers:
`MayAction` (→ `optional` on its child), `If`/`Unless` (`args=[condition,[actions]]`),
`IfElse` (`args=[condition,[then],[else]]`), and the `_Actions: "Targeted"` wrapper
(`args=[[targets], actionlist]` → mark contained effects `targeted=True`).

- [ ] **Step 1: Write the failing test (append to `test_fp_project.py`)**

```python
from fingerprints.project import extract_effects  # noqa: E402


def test_extract_simple_damage_each_creature():
    # Blasphemous Act body: SpellDealsDamage 13 to EachPermanent(Creature)
    actions = [{
        "_Action": "SpellDealsDamage",
        "args": [
            {"_Spell": "ThisSpell"},
            {"_GameNumber": "Integer", "args": 13},
            {"_DamageRecipient": "EachPermanent",
             "args": {"_Permanents": "IsCardtype", "args": "Creature"}},
        ],
    }]
    effs = extract_effects(actions)
    assert len(effs) == 1
    e = effs[0]
    assert e.verb == "SpellDealsDamage"
    assert e.object == "Creature" and e.quantifier == "each"
    assert e.amount.value == 13 and e.targeted is False


def test_extract_may_sets_optional():
    actions = [{"_Action": "MayAction",
                "args": {"_Action": "DrawACard"}}]
    effs = extract_effects(actions)
    assert len(effs) == 1
    assert effs[0].verb == "DrawACard" and effs[0].optional is True


def test_extract_targeted_flag():
    # Cruel Edict body: Targeted wrapper -> PlayerAction -> SacrificeAPermanent
    actions = [{
        "_Actions": "Targeted",
        "args": [
            [{"_Target": "TargetPlayer", "args": {"_Players": "Opponent"}}],
            {"_Actions": "ActionList", "args": [
                {"_Action": "PlayerAction", "args": [
                    {"_Player": "Ref_TargetPlayer"},
                    {"_Action": "SacrificeAPermanent",
                     "args": {"_Permanents": "IsCardtype", "args": "Creature"}},
                ]},
            ]},
        ],
    }]
    effs = extract_effects(actions)
    verbs = {e.verb for e in effs}
    assert "SacrificeAPermanent" in verbs
    assert any(e.targeted for e in effs)
```

Note: `extract_effects` returns a flat list; `optional`/`targeted` are carried on each `Effect`. Nested control-flow attaches as flags on the produced effects (v1 keeps it flat-with-flags; `sub_effects`/`condition` on the ability are populated by the caller in Task 5/6).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_fp_project.py -q`
Expected: FAIL — `ImportError: cannot import name 'extract_effects'`

- [ ] **Step 3: Implement `extract_effects`**

Append to `scoring/fingerprints/project.py`:
```python
# Action-arg slots that may carry an amount or a recipient/scope, by position-agnostic scan.
def _scan_amount(args: Any) -> Optional[Amount]:
    if isinstance(args, list):
        for a in args:
            amt = parse_amount(a)
            if amt:
                return amt
    return parse_amount(args)


def _scan_scope(args: Any) -> dict:
    candidates = args if isinstance(args, list) else [args]
    for a in candidates:
        sc = parse_scope(a) if isinstance(a, dict) else {"scope": None, "object": None, "quantifier": None}
        if any(sc.values()):
            return sc
    return {"scope": None, "object": None, "quantifier": None}


def _leaf_effect(node: dict, *, optional: bool, targeted: bool) -> Effect:
    args = node.get("args")
    sc = _scan_scope(args)
    return Effect(
        verb=node["_Action"],
        object=sc["object"], scope=sc["scope"], quantifier=sc["quantifier"],
        targeted=targeted, amount=_scan_amount(args),
    )
    # `optional` is applied by the caller via dataclasses.replace-style set below.


def extract_effects(actions: Any, *, optional: bool = False, targeted: bool = False,
                    depth: int = 0) -> list[Effect]:
    """Flatten an action list into Effects, honoring control-flow wrappers."""
    out: list[Effect] = []
    if depth > 25 or actions is None:
        return out
    items = actions if isinstance(actions, list) else [actions]
    for node in items:
        if not isinstance(node, dict):
            continue

        # Targeted wrapper: args = [[targets], actionlist]
        if node.get("_Actions") == "Targeted":
            inner = node.get("args") or []
            sub = inner[1] if len(inner) > 1 else None
            out.extend(extract_effects(sub, optional=optional, targeted=True, depth=depth + 1))
            continue

        # Plain action list container
        if node.get("_Actions") in ("ActionList", "Actions") or "_Actions" in node:
            out.extend(extract_effects(node.get("args"), optional=optional,
                                       targeted=targeted, depth=depth + 1))
            continue

        op = node.get("_Action")
        if op == "MayAction":
            out.extend(extract_effects(node.get("args"), optional=True,
                                       targeted=targeted, depth=depth + 1))
            continue
        if op in ("If", "Unless"):
            branch = node["args"][1] if isinstance(node.get("args"), list) and len(node["args"]) > 1 else None
            out.extend(extract_effects(branch, optional=optional, targeted=targeted, depth=depth + 1))
            continue
        if op == "IfElse":
            a = node.get("args") or []
            for branch in a[1:3]:
                out.extend(extract_effects(branch, optional=optional, targeted=targeted, depth=depth + 1))
            continue
        if op in ("PlayerAction", "EachPlayerAction", "MayActions"):
            # wrapper carrying a nested action (+ a player scope we fold into the child)
            out.extend(extract_effects(node.get("args"), optional=(op == "MayActions") or optional,
                                       targeted=targeted, depth=depth + 1))
            continue

        if op is not None:
            eff = _leaf_effect(node, optional=optional, targeted=targeted)
            if optional:
                eff.optional = True  # noqa: attribute set; Effect has no `optional` field by default
            out.append(eff)
    return out
```

Wait — `Effect` has no `optional` field. **Fix before implementing:** add `optional: bool = False` to `Effect` in `schema.py` (with serialization), then `eff.optional = optional` is valid. Update `schema.py` `Effect`:
- add field `optional: bool = False`
- in `to_dict`: add `"optional": self.optional`
- in `from_dict`: add `optional=bool(d.get("optional", False))`

And update Task 1's `test_ability_record_roundtrip` is unaffected (defaults). Then in `_leaf_effect` drop the trailing comment and let the caller set `eff.optional`.

- [ ] **Step 4: Apply the schema fix, then run tests**

Edit `scoring/fingerprints/schema.py` `Effect` per the note above. Then run:
`cd scoring && python -m pytest tests/test_fp_project.py tests/test_fp_schema.py -q`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add scoring/fingerprints/project.py scoring/fingerprints/schema.py scoring/tests/test_fp_project.py
git commit -m "feat(fp): extract effects through Targeted/May/If/Unless control flow"
```

---

### Task 5: Ability classification (kind, cost, trigger, condition)

**Files:**
- Modify: `scoring/fingerprints/project.py`
- Test: `scoring/tests/test_fp_project.py`

Real shapes: `{"_Rule":"TriggerA","args":[<trigger>, <actionlist>]}`; `{"_Rule":"Activated","args":[<cost>, <actionlist>]}`; `{"_Rule":"SpellActions","args":<actionlist>}`; keyword rules `{"_Rule":"Flying"}`; replacement-ish `{"_Rule":"AsPermanentEnters",...}`. Cost: `{"_Cost":"TapPermanent",...}`. Condition appears as an `If`/`Unless` `_Condition` node.

- [ ] **Step 1: Write the failing test (append to `test_fp_project.py`)**

```python
from fingerprints.project import project_rule  # noqa: E402


def test_project_triggered_etb_draw():
    rule = {"_Rule": "TriggerA", "args": [
        {"_Trigger": "WhenAPermanentEntersTheBattlefield",
         "args": {"_Permanents": "SinglePermanent", "args": {"_Permanent": "ThisPermanent"}}},
        {"_Actions": "ActionList", "args": [{"_Action": "DrawACard"}]},
    ]}
    rec = project_rule(rule, 0)
    assert rec.kind == "triggered"
    assert rec.trigger["op"] == "WhenAPermanentEntersTheBattlefield"
    assert [e.verb for e in rec.effects] == ["DrawACard"]


def test_project_activated_tap_for_mana():
    rule = {"_Rule": "Activated", "args": [
        {"_Cost": "TapPermanent", "args": {"_Permanent": "ThisPermanent"}},
        {"_Actions": "ActionList", "args": [
            {"_Action": "AddMana", "args": {"_ManaProduce": "And", "args": [
                {"_ManaProduce": "ManaProduceC"}, {"_ManaProduce": "ManaProduceC"}]}}]},
    ]}
    rec = project_rule(rule, 1)
    assert rec.kind == "activated"
    assert rec.cost["tap"] is True
    assert [e.verb for e in rec.effects] == ["AddMana"]


def test_project_static_keyword():
    rec = project_rule({"_Rule": "Flying"}, 2)
    assert rec.kind == "static"
    assert rec.raw == {"_Rule": "Flying"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_fp_project.py -q`
Expected: FAIL — `ImportError: cannot import name 'project_rule'`

- [ ] **Step 3: Implement `project_rule`**

Append to `scoring/fingerprints/project.py`:
```python
_REPLACEMENT_RULES = {
    "AsPermanentEnters", "ReplaceWouldEnter", "ReplaceWouldDraw",
    "ReplaceWouldDealDamage", "ReplaceWouldLeaveTheBattlefield",
    "ReplaceWouldDestroy", "ReplaceWouldDiscard", "ReplaceWouldMill",
}
_TRIGGER_RULES = {"TriggerA", "TriggerAll", "Trigger"}
_SPELL_RULES = {"SpellActions", "CastEffect"}


def _rule_kind(rule_op: str) -> str:
    if rule_op in _TRIGGER_RULES:
        return "triggered"
    if rule_op == "Activated":
        return "activated"
    if rule_op in _SPELL_RULES:
        return "spell"
    if rule_op in _REPLACEMENT_RULES:
        return "replacement"
    return "static"


def _find_first(node: Any, key: str, depth: int = 0) -> Optional[dict]:
    if depth > 6 or not isinstance(node, (dict, list)):
        return None
    if isinstance(node, dict):
        if key in node:
            return node
        for v in node.values():
            r = _find_first(v, key, depth + 1)
            if r is not None:
                return r
    else:
        for v in node:
            r = _find_first(v, key, depth + 1)
            if r is not None:
                return r
    return None


def _parse_cost(rule_args: Any) -> Optional[dict]:
    cost: dict = {}
    items = rule_args if isinstance(rule_args, list) else [rule_args]
    for a in items:
        if isinstance(a, dict) and "_Cost" in a:
            c = a["_Cost"]
            if c == "TapPermanent":
                cost["tap"] = True
            elif c == "Sacrifice" or "Sacrifice" in str(c):
                cost["sacrifice"] = True
            else:
                cost.setdefault("other", []).append(c)
    return cost or None


def _find_action_list(rule_args: Any) -> Any:
    """The arg element that is an action list (has _Actions or is a list of _Action)."""
    items = rule_args if isinstance(rule_args, list) else [rule_args]
    for a in items:
        if isinstance(a, dict) and "_Actions" in a:
            return a
        if isinstance(a, list) and any(isinstance(x, dict) and "_Action" in x for x in a):
            return a
    return None


def project_rule(rule: dict, idx: int) -> AbilityRecord:
    rule_op = rule.get("_Rule", "")
    kind = _rule_kind(rule_op)
    args = rule.get("args")

    trigger = None
    tnode = _find_first(rule, "_Trigger")
    if tnode is not None:
        trigger = {"op": tnode["_Trigger"], "raw": tnode.get("args")}

    cost = _parse_cost(args)

    condition = None
    cnode = _find_first(args, "_Condition")
    if cnode is not None:
        condition = {"op": cnode["_Condition"], "raw": cnode.get("args")}

    action_list = _find_action_list(args)
    effects = extract_effects(action_list)
    optional_ability = any(e.optional for e in effects) and len(effects) == 1

    return AbilityRecord(
        ability_idx=idx, kind=kind, trigger=trigger, cost=cost,
        condition=condition, optional=optional_ability,
        effects=effects, raw=rule,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_fp_project.py -q`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add scoring/fingerprints/project.py scoring/tests/test_fp_project.py
git commit -m "feat(fp): classify ability kind + parse cost/trigger/condition"
```

---

### Task 6: `project_card` (top-level)

**Files:**
- Modify: `scoring/fingerprints/project.py`
- Test: `scoring/tests/test_fp_project.py`

- [ ] **Step 1: Write the failing test (append to `test_fp_project.py`)**

```python
from fingerprints.project import project_card  # noqa: E402


def test_project_card_multi_rule():
    card = {"Name": "X", "Rules": [
        {"_Rule": "Flying"},
        {"_Rule": "TriggerA", "args": [
            {"_Trigger": "WhenAPermanentEntersTheBattlefield",
             "args": {"_Permanents": "SinglePermanent", "args": {"_Permanent": "ThisPermanent"}}},
            {"_Actions": "ActionList", "args": [{"_Action": "DrawACard"}]}]},
    ]}
    recs = project_card(card)
    assert [r.ability_idx for r in recs] == [0, 1]
    assert recs[0].kind == "static" and recs[1].kind == "triggered"


def test_project_card_empty_for_vanilla():
    assert project_card({"Name": "Grizzly Bears", "Rules": []}) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_fp_project.py -q`
Expected: FAIL — `ImportError: cannot import name 'project_card'`

- [ ] **Step 3: Implement `project_card`**

Append to `scoring/fingerprints/project.py`:
```python
def project_card(card: dict) -> list[AbilityRecord]:
    """Project a full MTGish card into ability records (one per top-level Rule)."""
    rules = card.get("Rules") or []
    return [project_rule(r, i) for i, r in enumerate(rules) if isinstance(r, dict)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_fp_project.py -q`
Expected: PASS (14 passed)

- [ ] **Step 5: Commit**

```bash
git add scoring/fingerprints/project.py scoring/tests/test_fp_project.py
git commit -m "feat(fp): project_card builds per-ability records for a whole card"
```

---

### Task 7: Derive layer — flat tags with new namespaces

**Files:**
- Create: `scoring/fingerprints/derive.py`
- Test: `scoring/tests/test_fp_derive.py`

Reuses `tag_taxonomy.ACTION_MAP`/`TRIGGER_MAP` for verb/trigger naming, and adds the new
namespaces (`q:`, `amt:`, `cost:`, `tgts:`, `may:`, `cond:`). Must make "burn each" vs "burn one targeted" produce different tag sets.

- [ ] **Step 1: Write the failing test**

Create `scoring/tests/test_fp_derive.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fingerprints.schema import Amount, Effect, AbilityRecord  # noqa: E402
from fingerprints.derive import flat_tags  # noqa: E402


def _dmg(scope, quant, targeted):
    return AbilityRecord(ability_idx=0, kind="spell", effects=[Effect(
        verb="SpellDealsDamage", object="Creature", scope=scope,
        quantifier=quant, targeted=targeted, amount=Amount("literal", 13))])


def test_burn_each_vs_one_differ():
    each = flat_tags([_dmg("EachPermanent", "each", False)])
    one = flat_tags([_dmg("SinglePermanent", "single", True)])
    assert each != one
    assert "q:each" in each and "q:single" in one
    assert "tgts:targeted" in one and "tgts:targeted" not in each


def test_verb_maps_to_effect_tag():
    tags = flat_tags([_dmg("EachPermanent", "each", False)])
    assert "e:damage" in tags          # via ACTION_MAP[SpellDealsDamage]


def test_amount_bucket_present():
    tags = flat_tags([_dmg("EachPermanent", "each", False)])
    assert any(t.startswith("amt:") for t in tags)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_fp_derive.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fingerprints.derive'`

- [ ] **Step 3: Implement `flat_tags`**

Create `scoring/fingerprints/derive.py`:
```python
"""Derive flat tags / inverted index / feature vectors from AbilityRecords.

Pure projection of the canonical records. Reuses the existing tag_taxonomy maps
for verb/trigger naming and adds quantifier/amount/cost/targeting/optional/
condition namespaces so 'burn-each' and 'burn-one-targeted' are distinguishable.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tag_taxonomy import (  # noqa: E402
    ACTION_MAP, TRIGGER_MAP, PERMANENT_CARDTYPE_MAP,
)

from .schema import AbilityRecord, Effect, Amount  # noqa: E402


def _amount_bucket(amt: Amount | None) -> str | None:
    if amt is None:
        return None
    if amt.kind == "dynamic":
        return "amt:dynamic"
    if amt.kind == "x":
        return "amt:x"
    v = amt.value or 0
    if v <= 1:
        return "amt:low"
    if v <= 3:
        return "amt:mid"
    return "amt:high"


def _effect_tags(e: Effect) -> set[str]:
    tags: set[str] = set(ACTION_MAP.get(e.verb, []))
    if e.quantifier:
        tags.add(f"q:{e.quantifier}")
    if e.targeted:
        tags.add("tgts:targeted")
    if e.optional:
        tags.add("may:optional")
    if e.object:
        tags.update(PERMANENT_CARDTYPE_MAP.get(e.object, []))
    bucket = _amount_bucket(e.amount)
    if bucket:
        tags.add(bucket)
    for sub in e.sub_effects:
        tags |= _effect_tags(sub)
    return tags


def flat_tags(records: list[AbilityRecord]) -> list[str]:
    """Per-card union of derived tags (sorted, deterministic)."""
    tags: set[str] = set()
    for rec in records:
        if rec.trigger:
            tags.update(TRIGGER_MAP.get(rec.trigger.get("op", ""), []))
        if rec.cost:
            if rec.cost.get("tap"):
                tags.add("cost:tap")
            if rec.cost.get("sacrifice"):
                tags.add("cost:sacrifice")
        if rec.condition:
            tags.add("cond:gated")
        if rec.optional:
            tags.add("may:optional")
        for e in rec.effects:
            tags |= _effect_tags(e)
    return sorted(tags)


def ability_tag_lists(records: list[AbilityRecord]) -> list[list[str]]:
    """One sorted tag list per ability (keeps ability_idx alignment)."""
    return [sorted(_per_ability_tags(rec)) for rec in records]


def _per_ability_tags(rec: AbilityRecord) -> set[str]:
    return set(flat_tags([rec]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_fp_derive.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scoring/fingerprints/derive.py scoring/tests/test_fp_derive.py
git commit -m "feat(fp): derive flat tags with quantifier/amount/cost/targeting"
```

---

### Task 8: Derive layer — inverted index + feature-vector seam

**Files:**
- Modify: `scoring/fingerprints/derive.py`
- Test: `scoring/tests/test_fp_derive.py`

- [ ] **Step 1: Write the failing test (append to `test_fp_derive.py`)**

```python
from fingerprints.derive import build_inverted_index, fingerprint_to_vector  # noqa: E402


def test_inverted_index_groups_cards_by_tag():
    per_card = {"card_a": ["e:damage", "q:each"], "card_b": ["e:damage"]}
    idx = build_inverted_index(per_card)
    assert sorted(idx["e:damage"]) == ["card_a", "card_b"]
    assert idx["q:each"] == ["card_a"]


def test_fingerprint_to_vector_counts_axes():
    rec = AbilityRecord(ability_idx=0, kind="spell", effects=[Effect(
        verb="SpellDealsDamage", object="Creature", scope="EachPermanent",
        quantifier="each", targeted=False, amount=Amount("literal", 13))])
    vec = fingerprint_to_vector([rec])
    assert vec["kind:spell"] == 1
    assert vec["verb:SpellDealsDamage"] == 1
    assert vec["q:each"] == 1
    assert vec["targeted"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_fp_derive.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_inverted_index'`

- [ ] **Step 3: Implement both functions**

Append to `scoring/fingerprints/derive.py`:
```python
from collections import defaultdict  # noqa: E402


def build_inverted_index(per_card_tags: dict[str, list[str]]) -> dict[str, list[str]]:
    """tag -> sorted list of card ids."""
    inv: dict[str, set[str]] = defaultdict(set)
    for card_id, tags in per_card_tags.items():
        for t in tags:
            inv[t].add(card_id)
    return {t: sorted(ids) for t, ids in inv.items()}


def fingerprint_to_vector(records: list[AbilityRecord]) -> dict[str, int]:
    """Structured feature vector (sparse dict).

    SP1 owns the final shape/weighting; this is the documented seam and is
    designed for late fusion with an SP3 co-occurrence embedding. Counts are
    interpretable and stand alone for cold-start (unseen) cards.
    """
    vec: dict[str, int] = defaultdict(int)
    vec["targeted"] = 0
    for rec in records:
        vec[f"kind:{rec.kind}"] += 1
        if rec.cost and rec.cost.get("tap"):
            vec["cost:tap"] += 1
        if rec.condition:
            vec["cond:gated"] += 1
        for e in _iter_effects(rec.effects):
            vec[f"verb:{e.verb}"] += 1
            if e.quantifier:
                vec[f"q:{e.quantifier}"] += 1
            if e.targeted:
                vec["targeted"] += 1
            if e.amount:
                vec[f"amt:{e.amount.kind}"] += 1
    return dict(vec)


def _iter_effects(effects: list[Effect]):
    for e in effects:
        yield e
        yield from _iter_effects(e.sub_effects)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_fp_derive.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add scoring/fingerprints/derive.py scoring/tests/test_fp_derive.py
git commit -m "feat(fp): inverted index + feature-vector seam for SP1"
```

---

### Task 9: QA harness (golden + coverage + unmapped-operator)

**Files:**
- Create: `scoring/fingerprints/qa.py`
- Test: `scoring/tests/test_fp_qa.py`

- [ ] **Step 1: Write the failing test**

Create `scoring/tests/test_fp_qa.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fingerprints.schema import AbilityRecord, Effect, Amount  # noqa: E402
from fingerprints.qa import golden_diff, unmapped_operators  # noqa: E402


def test_golden_diff_match():
    rec = AbilityRecord(ability_idx=0, kind="spell",
                        effects=[Effect(verb="DrawACard")])
    assert golden_diff([rec], [rec.to_dict()]) == []


def test_golden_diff_mismatch_reports():
    a = AbilityRecord(ability_idx=0, kind="spell", effects=[Effect(verb="DrawACard")])
    b = AbilityRecord(ability_idx=0, kind="spell", effects=[Effect(verb="Scry")])
    diff = golden_diff([a], [b.to_dict()])
    assert diff and "ability_idx 0" in diff[0]


def test_unmapped_operators_lists_unknown():
    # ACTION_MAP knows DrawACard; "FrobnicateWidget" is invented/unknown
    cards = [{"Rules": [{"_Rule": "SpellActions", "args": [
        {"_Action": "DrawACard"}, {"_Action": "FrobnicateWidget"}]}]}]
    report = unmapped_operators(cards)
    names = {op for op, _count in report}
    assert "FrobnicateWidget" in names
    assert "DrawACard" not in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_fp_qa.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fingerprints.qa'`

- [ ] **Step 3: Implement the QA functions**

Create `scoring/fingerprints/qa.py`:
```python
"""QA gates: golden regression, coverage report, unmapped-operator report."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tag_taxonomy import ACTION_MAP, TRIGGER_MAP  # noqa: E402

from .schema import AbilityRecord  # noqa: E402


def golden_diff(records: list[AbilityRecord], golden: list[dict]) -> list[str]:
    """Return human-readable diffs; empty list == exact match."""
    diffs: list[str] = []
    got = [r.to_dict() for r in records]
    if len(got) != len(golden):
        diffs.append(f"ability count {len(got)} != golden {len(golden)}")
    for i, (g, e) in enumerate(zip(got, golden)):
        if g != e:
            diffs.append(f"ability_idx {i} differs")
    return diffs


def _collect_ops(node: Any, kind: str, seen: Counter, depth: int = 0) -> None:
    if depth > 25:
        return
    if isinstance(node, dict):
        v = node.get(kind)
        if isinstance(v, str):
            seen[v] += 1
        for x in node.values():
            _collect_ops(x, kind, seen, depth + 1)
    elif isinstance(node, list):
        for x in node:
            _collect_ops(x, kind, seen, depth + 1)


def unmapped_operators(cards: list[dict]) -> list[tuple[str, int]]:
    """Operators present in the corpus that ACTION_MAP/TRIGGER_MAP don't name.

    Occurrence-weighted, descending. This is the shrinking backlog + new-set guard.
    """
    actions: Counter = Counter()
    triggers: Counter = Counter()
    for c in cards:
        _collect_ops(c.get("Rules", []), "_Action", actions)
        _collect_ops(c.get("Rules", []), "_Trigger", triggers)
    out: Counter = Counter()
    for op, n in actions.items():
        if op not in ACTION_MAP and op not in _STRUCTURAL:
            out[op] += n
    for op, n in triggers.items():
        if op not in TRIGGER_MAP:
            out[op] += n
    return out.most_common()


# Structural ops the projector handles directly (not "unmapped" leaf verbs).
_STRUCTURAL = {
    "If", "Unless", "IfElse", "MayAction", "MayActions",
    "PlayerAction", "EachPlayerAction",
}


def coverage_report(per_card_tags: dict[str, list[str]], total_cards: int) -> dict:
    nonempty = sum(1 for t in per_card_tags.values() if t)
    return {
        "total_cards": total_cards,
        "with_records": nonempty,
        "coverage_pct": round(100.0 * nonempty / total_cards, 2) if total_cards else 0.0,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_fp_qa.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scoring/fingerprints/qa.py scoring/tests/test_fp_qa.py
git commit -m "feat(fp): QA harness — golden diff, unmapped-operator, coverage"
```

---

### Task 10: Exclude acorn / Un-set cards in `prep_cards.py`

**Files:**
- Modify: `scoring/prep_cards.py` (the `_keep` function, ~line 44)
- Test: `scoring/tests/test_prep_cards.py`

Scryfall marks acorn/silver-border cards with `"security_stamp": "acorn"` and/or
`"border_color": "silver"`; funny sets carry `"set_type": "funny"`. We drop those.

- [ ] **Step 1: Write the failing test**

Create `scoring/tests/test_prep_cards.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prep_cards import _keep  # noqa: E402


def _base(**over):
    c = {"lang": "en", "layout": "normal",
         "legalities": {"commander": "legal"},
         "set_type": "expansion", "border_color": "black"}
    c.update(over)
    return c


def test_keep_normal_commander_card():
    assert _keep(_base()) is True


def test_drop_acorn_stamp():
    assert _keep(_base(security_stamp="acorn")) is False


def test_drop_silver_border():
    assert _keep(_base(border_color="silver")) is False


def test_drop_funny_set():
    assert _keep(_base(set_type="funny")) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_prep_cards.py -q`
Expected: FAIL — either ImportError (if `_keep` signature differs) or the acorn/silver/funny asserts fail.

- [ ] **Step 3: Add the exclusion to `_keep`**

In `scoring/prep_cards.py`, inside `_keep`, after the existing layout check and before the
legality return, add:
```python
    if card.get("security_stamp") == "acorn":
        return False
    if card.get("border_color") == "silver":
        return False
    if card.get("set_type") == "funny":
        return False
```
(Verify the existing `_keep` already reads `lang`, `layout`, and `legalities.commander`;
keep those checks intact — only add the three lines above.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_prep_cards.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add scoring/prep_cards.py scoring/tests/test_prep_cards.py
git commit -m "feat(fp): exclude acorn/silver-border/funny cards from corpus"
```

---

### Task 11: Orchestrator `build_fingerprints.py`

**Files:**
- Create: `scoring/build_fingerprints.py`
- Test: `scoring/tests/test_fp_build.py`

Wires it together: load MTGish + corpus, name-join (reuse `build_semantics.norm_name`),
project each matched card, merge hand-coded `data/outliers/*.json`, persist
`card_fingerprints` + `card_fingerprint_flat`, regenerate the derived
`card_ability_tags` / `card_flat_tags` / `tag_inverted_index` tables, then print
coverage + unmapped-operator reports.

- [ ] **Step 1: Write the failing integration test**

Create `scoring/tests/test_fp_build.py`:
```python
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_fingerprints import build  # noqa: E402


def test_build_end_to_end(tmp_path):
    mtgish = [{
        "Name": "Test Drawer",
        "Rules": [{"_Rule": "TriggerA", "args": [
            {"_Trigger": "WhenAPermanentEntersTheBattlefield",
             "args": {"_Permanents": "SinglePermanent", "args": {"_Permanent": "ThisPermanent"}}},
            {"_Actions": "ActionList", "args": [{"_Action": "DrawACard"}]}]}],
    }]
    cards = [{"id": "id-1", "name": "Test Drawer"}]
    mp = tmp_path / "mtgish.json"; mp.write_text(json.dumps(mtgish), encoding="utf-8")
    cp = tmp_path / "cards.json"; cp.write_text(json.dumps(cards), encoding="utf-8")
    db = tmp_path / "scores.sqlite"

    stats = build(str(mp), str(cp), str(db), outliers_dir=str(tmp_path / "none"))

    assert stats["matched"] == 1
    con = sqlite3.connect(db)
    rec = con.execute("select record from card_fingerprints where card_id='id-1'").fetchone()
    assert rec is not None
    fp = json.loads(rec[0])
    assert fp["kind"] == "triggered"
    flat = con.execute("select tags from card_flat_tags where card_id='id-1'").fetchone()
    assert "e:draw" in json.loads(flat[0])
    con.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scoring && python -m pytest tests/test_fp_build.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'build_fingerprints'`

- [ ] **Step 3: Implement `build_fingerprints.py`**

Create `scoring/build_fingerprints.py`:
```python
"""Orchestrate the card-fingerprint build: project -> persist -> derive -> QA.

Usage:
    python scoring/build_fingerprints.py \
        --mtgish C:/simmander/simmander/mtgish/data/cards.json \
        --cards  data/cards.json \
        --db     data/scores.sqlite
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_semantics import norm_name  # noqa: E402  (reuse the proven name join)
from fingerprints.project import project_card  # noqa: E402
from fingerprints.schema import AbilityRecord  # noqa: E402
from fingerprints.derive import (  # noqa: E402
    flat_tags, ability_tag_lists, build_inverted_index,
)
from fingerprints.qa import coverage_report, unmapped_operators  # noqa: E402


def _load_outliers(outliers_dir: str) -> dict[str, list[AbilityRecord]]:
    """data/outliers/*.json -> {card_id: [AbilityRecord,...]}.

    Each file: {"card_id": "...", "records": [<record dict>, ...]}.
    """
    out: dict[str, list[AbilityRecord]] = {}
    d = Path(outliers_dir)
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.json")):
        obj = json.loads(f.read_text(encoding="utf-8"))
        out[obj["card_id"]] = [AbilityRecord.from_dict(r) for r in obj["records"]]
    return out


def build(mtgish_path: str, cards_path: str, db_path: str,
          outliers_dir: str = "data/outliers") -> dict:
    mtgish = json.loads(Path(mtgish_path).read_text(encoding="utf-8"))
    raw = json.loads(Path(cards_path).read_text(encoding="utf-8"))
    cards = raw["data"] if isinstance(raw, dict) and "data" in raw else raw

    name_to_id = {norm_name(c["name"]): c["id"] for c in cards}
    outliers = _load_outliers(outliers_dir)

    fingerprints: dict[str, list[AbilityRecord]] = {}
    matched = 0
    for mc in mtgish:
        cid = name_to_id.get(norm_name(mc.get("Name", "")))
        if cid is None:
            continue
        fingerprints[cid] = project_card(mc)
        matched += 1
    fingerprints.update(outliers)  # hand-coded outliers win

    # Derive views
    per_card_tags = {cid: flat_tags(recs) for cid, recs in fingerprints.items()}

    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        DROP TABLE IF EXISTS card_fingerprints;
        CREATE TABLE card_fingerprints (
            card_id TEXT NOT NULL, ability_idx INTEGER NOT NULL,
            record TEXT NOT NULL, source TEXT, confidence REAL,
            PRIMARY KEY (card_id, ability_idx));
        DROP TABLE IF EXISTS card_fingerprint_flat;
        CREATE TABLE card_fingerprint_flat (
            card_id TEXT PRIMARY KEY, record TEXT NOT NULL);
        DROP TABLE IF EXISTS card_ability_tags;
        CREATE TABLE card_ability_tags (
            card_id TEXT NOT NULL, ability_idx INTEGER NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]', PRIMARY KEY (card_id, ability_idx));
        DROP TABLE IF EXISTS card_flat_tags;
        CREATE TABLE card_flat_tags (card_id TEXT PRIMARY KEY, tags TEXT NOT NULL DEFAULT '[]');
        DROP TABLE IF EXISTS tag_inverted_index;
        CREATE TABLE tag_inverted_index (tag TEXT PRIMARY KEY, card_ids TEXT NOT NULL DEFAULT '[]');
    """)

    for cid, recs in fingerprints.items():
        source = "outlier" if cid in outliers else "mtgish"
        for rec in recs:
            con.execute("INSERT OR REPLACE INTO card_fingerprints VALUES (?,?,?,?,?)",
                        (cid, rec.ability_idx, json.dumps(rec.to_dict()), source, 1.0))
        con.execute("INSERT OR REPLACE INTO card_fingerprint_flat VALUES (?,?)",
                    (cid, json.dumps([r.to_dict() for r in recs])))
        for idx, tags in enumerate(ability_tag_lists(recs)):
            con.execute("INSERT OR REPLACE INTO card_ability_tags VALUES (?,?,?)",
                        (cid, idx, json.dumps(tags)))
        con.execute("INSERT OR REPLACE INTO card_flat_tags VALUES (?,?)",
                    (cid, json.dumps(per_card_tags[cid])))

    inv = build_inverted_index(per_card_tags)
    con.executemany("INSERT INTO tag_inverted_index VALUES (?,?)",
                    [(t, json.dumps(ids)) for t, ids in inv.items()])
    con.commit()
    con.close()

    cov = coverage_report(per_card_tags, total_cards=len(cards))
    unmapped = unmapped_operators(mtgish)
    return {"matched": matched, "coverage": cov, "unmapped_top": unmapped[:25]}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mtgish", default="C:/simmander/simmander/mtgish/data/cards.json")
    p.add_argument("--cards", default="data/cards.json")
    p.add_argument("--db", default="data/scores.sqlite")
    p.add_argument("--outliers", default="data/outliers")
    a = p.parse_args()
    stats = build(a.mtgish, a.cards, a.db, outliers_dir=a.outliers)
    print(f"Matched {stats['matched']:,} cards")
    print(f"Coverage: {stats['coverage']}")
    print("Top unmapped operators (occurrence-weighted):")
    for op, n in stats["unmapped_top"]:
        print(f"  {n:>6}  {op}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scoring && python -m pytest tests/test_fp_build.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the full suite**

Run: `cd scoring && python -m pytest -q`
Expected: PASS (all fingerprint + existing evaluate tests)

- [ ] **Step 6: Commit**

```bash
git add scoring/build_fingerprints.py scoring/tests/test_fp_build.py
git commit -m "feat(fp): orchestrator builds canonical + derived tables end-to-end"
```

---

### Task 12: Real run, golden set, reports

**Files:**
- Create: `data/golden/*.json` (curated), `data/outliers/` (dir; may stay empty if corpus excludes acorn)
- Test: `scoring/tests/test_fp_golden.py`

- [ ] **Step 1: Run the real build and capture reports**

Run:
```bash
cd C:/simmander/simmander-deckbuilder
python scoring/prep_cards.py --src C:/simmander/simmander/data/default-cards.json --out data/cards.json
python scoring/build_fingerprints.py
```
Expected: prints `Matched ~30,9xx cards`, a `Coverage` dict, and the top-25 unmapped
operators. Save the unmapped list — it is the SP2 backlog.

- [ ] **Step 2: Curate the golden set**

For ~50–100 cards spanning the mechanic families (ETB draw, dies-trigger, activated
tap-for-mana, targeted removal, damage-to-each, -1/-1 counters, X spell, dynamic amount,
modal `ChooseAnAction`, replacement `AsPermanentEnters`, optional `MayAction`), dump the
projector output and hand-verify each, then save as golden fixtures:
```bash
cd scoring
python -c "import json,sys; sys.path.insert(0,'.'); from fingerprints.project import project_card; \
m={c['Name']:c for c in json.load(open('C:/simmander/simmander/mtgish/data/cards.json',encoding='utf-8'))}; \
name='Elvish Visionary'; recs=project_card(m[name]); \
open(f'../data/golden/{name.replace(chr(32),\"_\")}.json','w').write(json.dumps({'name':name,'records':[r.to_dict() for r in recs]},indent=1))"
```
Repeat for each chosen card; **eyeball every dumped record against the oracle text** before
trusting it as golden (golden must be *verified*, not just *generated*).

- [ ] **Step 3: Write the golden regression test**

Create `scoring/tests/test_fp_golden.py`:
```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fingerprints.project import project_card  # noqa: E402
from fingerprints.qa import golden_diff  # noqa: E402

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "data" / "golden"
MTGISH = Path("C:/simmander/simmander/mtgish/data/cards.json")


def _mtgish_by_name():
    return {c["Name"]: c for c in json.loads(MTGISH.read_text(encoding="utf-8"))}


def test_all_golden_match():
    if not GOLDEN_DIR.is_dir() or not list(GOLDEN_DIR.glob("*.json")):
        import pytest
        pytest.skip("no golden fixtures yet")
    by_name = _mtgish_by_name()
    failures = []
    for f in sorted(GOLDEN_DIR.glob("*.json")):
        obj = json.loads(f.read_text(encoding="utf-8"))
        recs = project_card(by_name[obj["name"]])
        diff = golden_diff(recs, obj["records"])
        if diff:
            failures.append(f"{obj['name']}: {diff}")
    assert not failures, "\n".join(failures)
```

- [ ] **Step 4: Run the golden regression**

Run: `cd scoring && python -m pytest tests/test_fp_golden.py -q`
Expected: PASS (golden fixtures reproduce exactly). If a card fails, either the projector
has a real gap (fix it) or the golden was wrong (re-verify) — do not "make it pass" blindly.

- [ ] **Step 5: Commit**

```bash
git add data/golden scoring/tests/test_fp_golden.py
git commit -m "test(fp): golden regression fixtures across mechanic families"
```

- [ ] **Step 6: Final full-suite run + push**

```bash
cd scoring && python -m pytest -q
cd .. && git push -u origin sp2-card-fingerprint
```
Expected: all tests pass; branch pushed.

---

## Self-review notes (author)

- **Spec coverage:** §4 schema → Tasks 1,4(fix). §4.2(1) targeted → Task 4. §4.2(2) amount → Task 2. §4.2(3) kinds → Task 5/schema. §4.2(4) condition/optional → Tasks 4,5. §5.1 projector structural recursion → Tasks 3–6. §5.2 acorn exclusion → Task 10. §5.3 derived views (flat tags new namespaces / inverted index / vector seam) → Tasks 7,8. §6 QA (golden/coverage/unmapped) → Tasks 9,12. §4.3 storage tables → Task 11. Modal (`ChooseAnAction`) is captured in `raw` and surfaced by the unmapped report; a dedicated `modal` parse is deferred (low frequency, ~37 cards) and listed as backlog rather than silently dropped.
- **Type consistency:** `Effect.optional` is added in Task 4's schema fix and consumed in Tasks 7/8. `AbilityRecord.to_dict()/from_dict()` used identically in Tasks 1, 9, 11. `flat_tags`, `ability_tag_lists`, `build_inverted_index`, `fingerprint_to_vector`, `project_card`, `project_rule`, `golden_diff`, `unmapped_operators`, `coverage_report`, `build` names match across tasks.
- **Known deferrals (explicit, not placeholders):** full leaf-operator naming coverage (incremental via the unmapped report); dedicated modal parsing; `cost` mana-symbol detail beyond tap/sacrifice. These are backlog items the QA report tracks, consistent with spec §6's "shrinking backlog" model.
