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
            eff.optional = optional
            out.append(eff)
    return out
