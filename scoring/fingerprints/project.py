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
