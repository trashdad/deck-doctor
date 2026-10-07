"""Reading MTGish rules trees across the April-2026 snapshot and the restructured upstream.

Upstream (https://github.com/i5jb/mtgish, 2026-10) folded whole operator families
into one `_Action` whose argument is a *variant node* naming the specific operation:

    April                                   upstream
    PutACounterOfTypeOnPermanent            PutCounters  + _PutCountersAction "ACounterOfTypeOnPermanent"
    ExilePermanent / ExileGraveyardCard     Exile        + [_Exilable "Permanent" / "CardInGraveyards"]
    RemoveACounterOfTypeFromPermanent       RemoveCounters + _RemoveCountersAction "ACounterOfTypeFromPermanent"
    _Cost RemoveACounterOfTypeFromPermanent _Cost RemoveCounters + _RemoveCountersCost "..."

It also moved "<trigger> while/if <condition>" into a `_Trigger: If` wrapper, gated
anchor-word abilities with `_Rule: AnchorWord`, and replaced "MayCost/MustCost X;
If CostWasPaid: ReflexiveTrigger(...)" with one `Reflexive_<step>_When...` action.

The consumers keep the variant as part of the verb (`PutCounters.ACounterOfTypeOnPermanent`)
so the old operator granularity survives: one April op corresponds to one qualified
upstream verb. Both shapes are accepted, so the April snapshot still projects unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

# Variant-node keys of folded `_Action`s and `_Cost`s.
ACTION_VARIANT_KEYS = ("_PutCountersAction", "_RemoveCountersAction", "_MoveCountersAction",
                       "_PutOrRemoveCountersAction", "_Exilable")
COST_VARIANT_KEYS = ("_PutCountersCost", "_RemoveCountersCost", "_MoveCountersCost", "_ExilableCost")

REFLEXIVE_PREFIX = "Reflexive_"


def load_mtgish(path: str | Path) -> list[dict]:
    """MTGish cards from a JSON array (April snapshot) or JSON lines (upstream mtgish.lines.json)."""
    with open(path, encoding="utf-8") as fh:
        head = fh.read(1)
        while head and head.isspace():
            head = fh.read(1)
        fh.seek(0)
        if head == "[":
            return json.load(fh)
        return [json.loads(line) for line in fh if line.strip()]


def _items(args: Any) -> list:
    """Args as a flat list: a lone node becomes [node]; one level of nested lists is opened."""
    out: list = []
    for a in (args if isinstance(args, list) else [args]):
        if isinstance(a, list):
            out.extend(a)
        else:
            out.append(a)
    return out


def variant_nodes(node: dict, keys: Iterable[str] = ACTION_VARIANT_KEYS) -> list[tuple[str, dict]]:
    """[(variant name, variant node), ...] directly under an action/cost node's args."""
    keys = tuple(keys)
    out = []
    for a in _items(node.get("args")):
        if isinstance(a, dict):
            for k in keys:
                if isinstance(a.get(k), str):
                    out.append((a[k], a))
                    break
    return out


def action_extras(node: dict, keys: Iterable[str] = ACTION_VARIANT_KEYS) -> list[dict]:
    """The other nodes under a folded action's args (e.g. Exile's _ExileFlag list)."""
    keys = tuple(keys)
    return [a for a in _items(node.get("args"))
            if isinstance(a, dict) and not any(isinstance(a.get(k), str) for k in keys)]


def token_list(node: dict) -> list[dict] | None:
    """The `_CreatableToken` list of an upstream token maker ([[tokens], [flags]] or
    [selector, [tokens], [flags]]); None for the April shape (token nodes as args)."""
    args = node.get("args")
    for a in (args if isinstance(args, list) else []):
        if isinstance(a, list) and any(isinstance(t, dict) and "_CreatableToken" in t for t in a):
            return [t for t in a if isinstance(t, dict)]
    return None


def nested_actions(args: Any, depth: int = 0) -> list[dict]:
    """`_Action` / `_Actions` nodes held directly in an action's args (through up to two
    list levels, e.g. ChooseAnAction's [[option], [option]])."""
    out: list[dict] = []
    for a in (args if isinstance(args, list) else [args]):
        if isinstance(a, dict) and ("_Action" in a or "_Actions" in a):
            out.append(a)
        elif isinstance(a, list) and depth < 2:
            out.extend(nested_actions(a, depth + 1))
    return out


def qualify(op: str, variant: str | None) -> str:
    return f"{op}.{variant}" if variant else op


def action_verbs(node: dict) -> list[str]:
    """Verb(s) of an `_Action` node: one qualified verb per variant, else the plain op."""
    op = node.get("_Action")
    if not isinstance(op, str):
        return []
    variants = variant_nodes(node)
    if variants:
        return [qualify(op, v) for v, _ in variants]
    return [op]


def cost_op(node: dict) -> str:
    """The `_Cost` op, qualified with its variant when upstream folded it."""
    op = node.get("_Cost", "")
    variants = variant_nodes(node, COST_VARIANT_KEYS)
    return qualify(op, variants[0][0]) if variants else op


def is_reflexive(op: Any) -> bool:
    """Reflexive_<step>_When... actions, and the one non-prefixed form upstream has
    (RegeneratePermanent_WhenItRengeratesThisWay)."""
    return isinstance(op, str) and (op.startswith(REFLEXIVE_PREFIX) or "_When" in op)


def reflexive_steps(op: str) -> list[str]:
    """What you do before "when you do": Reflexive_PayMana_Sacrifice_WhenYouDo -> [PayMana, Sacrifice]."""
    if not is_reflexive(op):
        return []
    body = op[len(REFLEXIVE_PREFIX):] if op.startswith(REFLEXIVE_PREFIX) else op
    steps = []
    for part in body.split("_"):
        if part.startswith("When") or part == "If":
            break
        steps.append(part)
    return steps


def reflexive_split(node: dict) -> tuple[list, list[dict]]:
    """(step args, reflexive bodies) of a Reflexive_* action: bodies are the `_Actions` args."""
    args = node.get("args")
    items = args if isinstance(args, list) else [args]
    bodies = [a for a in items if isinstance(a, dict) and "_Actions" in a]
    steps = [a for a in items if not (isinstance(a, dict) and "_Actions" in a)]
    return steps, bodies


def core_trigger(tnode: dict) -> dict:
    """Unwrap `_Trigger: If` ([condition, trigger]) down to the real trigger node."""
    seen = 0
    while tnode.get("_Trigger") == "If" and seen < 8:
        args = tnode.get("args")
        inner = next((a for a in (args if isinstance(args, list) else [])
                      if isinstance(a, dict) and "_Trigger" in a), None)
        if inner is None:
            break
        tnode = inner
        seen += 1
    return tnode


def trigger_ops(trigger: dict | None) -> list[str]:
    """A record trigger's op plus every `_Trigger` op nested in its raw args (the parts
    of an "Or" trigger, the trigger inside an "If")."""
    if not trigger:
        return []
    ops: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            t = node.get("_Trigger")
            if isinstance(t, str) and t not in ops:
                ops.append(t)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    op = trigger.get("op")
    if isinstance(op, str):
        ops.append(op)
    walk(trigger.get("raw"))
    return ops


def anchor_word(rule: dict) -> tuple[str, dict] | None:
    """(word, inner rule) for `_Rule: AnchorWord` ([word, rule]), else None."""
    if rule.get("_Rule") != "AnchorWord":
        return None
    args = rule.get("args")
    if (isinstance(args, list) and len(args) == 2 and isinstance(args[1], dict)
            and "_Rule" in args[1]):
        return args[0], args[1]
    return None


def core_rule(rule: dict) -> dict:
    """The rule an AnchorWord wrapper gates (the rule itself otherwise)."""
    aw = anchor_word(rule)
    return core_rule(aw[1]) if aw else rule
