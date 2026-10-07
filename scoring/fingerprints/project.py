"""Project MTGish typed `Rules` trees into structured AbilityRecords.

Canonical `verb` is the raw MTGish `_Action` operator string (lossless); curated
naming is the derive layer's job. The projector handles the structural skeleton
(rule kind, cost, trigger, action lists, control-flow wrappers, amounts, scope,
targeting) and leaves unknown leaf ops as raw verbs (surfaced by the QA
unmapped-operator report).

Upstream MTGish (2026-10) folded operator families into one op plus a variant node
(PutCounters + _PutCountersAction, Exile + _Exilable, ...). Such an action becomes
one Effect per variant with verb "<op>.<variant>" (e.g. "Exile.Permanent"), read from
the variant node's args, so each April op still maps to exactly one verb. See
mtgish_schema.py for the other upstream wrappers handled here (_Trigger If,
_Rule AnchorWord, Reflexive_* actions).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tag_taxonomy import COUNTER_MAP, PLAYER_MAP, PLAYERS_MAP  # noqa: E402
from mtgish_schema import (  # noqa: E402
    action_extras, anchor_word, core_trigger, cost_op, is_reflexive, nested_actions, qualify,
    reflexive_split, token_list, variant_nodes,
)

from .schema import Amount, Effect, AbilityRecord


# Search depth for counters / card types under an effect's args. Upstream nests folded
# operators 2-3 levels deeper than April, so a second, deeper pass runs only when the
# April-depth pass finds nothing (it never changes what the April-depth pass finds).
_SCAN_DEPTH = 8
_SCAN_DEPTH_UPSTREAM = 11


def parse_counter(node: Any, depth: int = 0, limit: Optional[int] = None) -> Optional[str]:
    """Find a `_CounterType` under a node and return its slug (plus1/minus1/poison/...)."""
    if limit is None:
        return (parse_counter(node, depth, _SCAN_DEPTH)
                or parse_counter(node, depth, _SCAN_DEPTH_UPSTREAM))
    if depth > limit or not isinstance(node, (dict, list)):
        return None
    if isinstance(node, dict):
        if "_CounterType" in node:
            ct = node["_CounterType"]
            if ct == "PTCounter":
                args = node.get("args")
                if args == [1, 1]:
                    return "plus1"
                if args == [-1, -1]:
                    return "minus1"
                return "pt_counter"
            tags = COUNTER_MAP.get(ct)        # e.g. "PoisonCounter" -> ["c:poison"]
            if tags:
                return tags[0].split(":", 1)[1]
            return None
        for v in node.values():
            r = parse_counter(v, depth + 1, limit)
            if r:
                return r
    else:
        for v in node:
            r = parse_counter(v, depth + 1, limit)
            if r:
                return r
    return None


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
            # "IsCardtype" is a type FILTER, not a scope token; the object type is
            # set below by _find_cardtype, so don't pollute scope with it.
            if wrapper == "_Permanents" and token == "IsCardtype":
                break
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


def _find_cardtype(node: Any, depth: int = 0, limit: Optional[int] = None) -> Optional[str]:
    """Find the first `_Permanents: IsCardtype` cardtype string under a node."""
    if limit is None:
        return (_find_cardtype(node, depth, _SCAN_DEPTH)
                or _find_cardtype(node, depth, _SCAN_DEPTH_UPSTREAM))
    if depth > limit or not isinstance(node, (dict, list)):
        return None
    if isinstance(node, dict):
        if node.get("_Permanents") == "IsCardtype" and isinstance(node.get("args"), str):
            return node["args"]
        for v in node.values():
            r = _find_cardtype(v, depth + 1, limit)
            if r:
                return r
    else:
        for v in node:
            r = _find_cardtype(v, depth + 1, limit)
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
    # NOTE: grants / duration / prefixes are first-class schema fields but the
    # projector does not extract them yet (deferred backlog per the fingerprint
    # spec §4/§6 — modal, durations, granted keywords). They stay at their
    # defaults until a dedicated pass adds them; the canonical `raw` preserves
    # the source data so no information is lost.
    args = node.get("args")
    sc = _scan_scope(args)
    return Effect(
        verb=node["_Action"],
        object=sc["object"], scope=sc["scope"], quantifier=sc["quantifier"],
        targeted=targeted, counter=parse_counter(args), amount=_scan_amount(args),
    )


def _scan_amount_in(nodes: list) -> Optional[Amount]:
    """First amount among nodes or their args (flag nodes carry theirs in args)."""
    for n in nodes:
        amt = parse_amount(n) or (_scan_amount(n.get("args")) if isinstance(n, dict) else None)
        if amt:
            return amt
    return None


def _graveyard_owner(variant: str, vargs: Any) -> Optional[str]:
    """Whose graveyard a graveyard-card operation reads. April named the player in the
    op (ExileEachPlayersGraveyard {AnyPlayer}, ExileEachCardFromPlayersGraveyard {You});
    upstream puts it in the card filter (InAPlayersGraveyard / AnyCardInAnyGraveyard),
    and "each card in graveyards" without an owner filter means all graveyards."""
    found: list = []

    def walk(n: Any, depth: int = 0) -> None:
        if found or depth > _SCAN_DEPTH_UPSTREAM or not isinstance(n, (dict, list)):
            return
        if isinstance(n, dict):
            v = n.get("_CardsInGraveyards")
            if v == "AnyCardInAnyGraveyard":
                found.append("AnyPlayer")
                return
            if v == "InAPlayersGraveyard" and isinstance(n.get("args"), dict):
                players = n["args"]
                inner = players.get("args")
                if (players.get("_Players") == "SinglePlayer" and isinstance(inner, dict)
                        and isinstance(inner.get("_Player"), str)):
                    found.append(inner["_Player"])
                elif isinstance(players.get("_Players"), str):
                    found.append(players["_Players"])
                return
            for x in n.values():
                walk(x, depth + 1)
        else:
            for x in n:
                walk(x, depth + 1)

    walk(vargs)
    if found:
        return found[0]
    return "AnyPlayer" if variant.startswith("Each") else None


def _variant_effect(op: str, variant: str, vnode: dict, extras: list, *, targeted: bool) -> Effect:
    """One operation of a folded upstream action; its variant node holds what the
    April op's own args held (amount, counter, recipient). Counters/amounts that
    upstream moved into flags ("exile it with three time counters") come from extras."""
    vargs = vnode.get("args")
    sc = _scan_scope(vargs)
    scope, obj = sc["scope"], sc["object"]
    if scope is None and "Graveyard" in variant:
        scope = _graveyard_owner(variant, vargs)
        if scope is not None and obj is None:
            obj = "player"
    return Effect(
        verb=qualify(op, variant),
        object=obj, scope=scope, quantifier=sc["quantifier"],
        targeted=targeted,
        counter=parse_counter(vargs) or parse_counter(extras),
        amount=_scan_amount(vargs) or _scan_amount_in(extras),
    )


def _token_effect(node: dict, tokens: list[dict], *, targeted: bool) -> Effect:
    """Upstream token makers hold their tokens in a list ([[tokens], [flags]]); read the
    object from the tokens as April did from its token-node args, the scope from a
    leading player/permanent selector when the tokens give none."""
    args = node.get("args")
    head = [a for a in (args if isinstance(args, list) else [args]) if isinstance(a, dict)]
    sc = _scan_scope(tokens)
    sc_head = _scan_scope(head)
    scope = sc["scope"] if sc["scope"] is not None else sc_head["scope"]
    obj = sc["object"] if sc["object"] is not None else (
        sc_head["object"] if sc_head["object"] != "player" else None)
    return Effect(
        verb=node["_Action"],
        object=obj, scope=scope, quantifier=sc["quantifier"],
        targeted=targeted, counter=parse_counter(args), amount=_scan_amount(tokens),
    )


def _fold_player_scope(children: list[Effect], scope: Optional[str]) -> None:
    """Give an each-player action's player scope to children whose own scope is not a
    player scope (none, or a permanent filter)."""
    if scope is None:
        return
    for child in children:
        if child.scope is None or (child.object != "player" and child.scope not in PLAYER_MAP
                                   and child.scope not in PLAYERS_MAP):
            child.scope = scope


# Upstream containers that now hold actions April listed next to them: "each player
# may pay X, else Y" (April: EachPlayerMayCost + EachPlayerAction(DidntPayCost, Y)) and
# "choose one: pay X / pay Y. When you do ..." (April: MayCost(Or) + ReflexiveTrigger).
_ACTION_CONTAINERS = {
    "EachPlayerMayCostOrFallback", "EachPlayerMayCostAndFallback",
    "ChooseAnAction", "ActionForEachPermanentExiledThisWay", "ActionForEachTarget",
}


def _has_do_nothing_option(args: Any) -> bool:
    """ChooseAnAction [[option], ..., [DoNothing]]: upstream's "you may X or Y"."""
    return isinstance(args, list) and any(
        isinstance(o, list) and len(o) == 1 and isinstance(o[0], dict)
        and o[0].get("_Action") == "DoNothing" for o in args)


def _reflexive_effect(node: dict, *, targeted: bool) -> Effect:
    """The step of a Reflexive_<step>_When... action ("sacrifice a creature. When you
    do, ..."). Scope/object come from the step's args first, then the reflexive body,
    as the April MayCost/MustCost and ReflexiveTrigger leaves captured them."""
    steps, bodies = reflexive_split(node)
    flat_steps: list = []
    for a in steps:
        flat_steps.extend(a if isinstance(a, list) else [a])
    sc = _scan_scope(flat_steps + bodies)
    return Effect(
        verb=node["_Action"],
        object=sc["object"], scope=sc["scope"], quantifier=sc["quantifier"],
        targeted=targeted, counter=parse_counter(node.get("args")),
        amount=_scan_amount_in(flat_steps),
    )


def _reflexive_body(body: Any, *, optional: bool, targeted: bool, depth: int) -> list[Effect]:
    """Effects of a "when you do" body. Those without an object take the body's first
    card type (usually its target's), which April's ReflexiveTrigger leaf carried."""
    effects = extract_effects(body, optional=optional, targeted=targeted, depth=depth)
    obj = _find_cardtype(body)
    if obj:
        for e in effects:
            if e.object is None:
                e.object = obj
    return effects


def _player_scope(args: Any) -> Optional[str]:
    """Scope token of the player node of a PlayerAction / EachPlayerAction wrapper."""
    for a in (args if isinstance(args, list) else [args]):
        if isinstance(a, dict) and ("_Player" in a or "_Players" in a):
            return parse_scope(a)["scope"]
    return None


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
        if op in ("PlayerAction", "EachPlayerAction", "MayActions", "EachPlayerMayAction"):
            # wrapper carrying a nested action (+ a player scope we fold into the child)
            may = op in ("MayActions", "EachPlayerMayAction")
            children = extract_effects(node.get("args"), optional=may or optional,
                                       targeted=targeted, depth=depth + 1)
            if op in ("EachPlayerAction", "EachPlayerMayAction"):
                # Upstream split April's EachPlayerActions leaf (which carried the
                # players scope itself) into one EachPlayerAction per action; fold
                # that scope into the children so it is not lost.
                _fold_player_scope(children, _player_scope(node.get("args")))
            out.extend(children)
            continue
        if op in ("ReflexiveTrigger", "ReflexiveTriggerNEW"):
            # "When you do, <actions>": a wrapper whose args are the action list
            out.extend(_reflexive_body(node.get("args"), optional=optional,
                                       targeted=targeted, depth=depth + 1))
            continue
        if is_reflexive(op):
            # upstream Reflexive_<step>_When...: the step itself, then the reflexive body
            eff = _reflexive_effect(node, targeted=targeted)
            eff.optional = optional
            out.append(eff)
            for body in reflexive_split(node)[1]:
                out.extend(_reflexive_body(body, optional=optional, targeted=targeted,
                                           depth=depth + 1))
            continue

        variants = variant_nodes(node) if op is not None else []
        if variants:
            extras = action_extras(node)
            for variant, vnode in variants:
                eff = _variant_effect(op, variant, vnode, extras, targeted=targeted)
                eff.optional = optional
                out.append(eff)
            continue

        tokens = token_list(node) if op is not None else None
        if tokens is not None:
            eff = _token_effect(node, tokens, targeted=targeted)
            eff.optional = optional
            out.append(eff)
            continue

        if op == "DoNothing":
            continue
        if op is not None:
            may = op == "ChooseAnAction" and _has_do_nothing_option(node.get("args"))
            eff = _leaf_effect(node, optional=optional or may, targeted=targeted)
            eff.optional = optional or may
            out.append(eff)
            if op in _ACTION_CONTAINERS:
                children = extract_effects(nested_actions(node.get("args")), optional=optional or may,
                                           targeted=targeted, depth=depth + 1)
                if op.startswith("EachPlayer"):
                    _fold_player_scope(children, _player_scope(node.get("args")))
                out.extend(children)
    return out


_REPLACEMENT_RULES = {
    "AsPermanentEnters", "ReplaceWouldEnter", "ReplaceWouldDraw",
    "ReplaceWouldDealDamage", "ReplaceWouldLeaveTheBattlefield",
    "ReplaceWouldDestroy", "ReplaceWouldDiscard", "ReplaceWouldMill",
    # Upstream moved damage prevention out of ReplaceWouldDealDamage; kept a
    # "replacement" (not "prevention") so those abilities project as before.
    "PreventDamage",
}
_TRIGGER_RULES = {"TriggerA", "TriggerAll", "Trigger"}
_SPELL_RULES = {"SpellActions", "CastEffect", "SpellActions_Teamwork"}


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


def _transparent(node: dict) -> bool:
    """Wrappers upstream added around structures April had bare: a Targeted action list
    (upstream "fixed missing targets") and `_Trigger: If`. Searches for an ability's
    gate do not count their nesting, so the gate is found at April's depth."""
    return node.get("_Actions") == "Targeted" or node.get("_Trigger") == "If"


def _find_gate(node: Any, match, depth: int = 0, flat: bool = False) -> Optional[dict]:
    """First dict satisfying `match` within 6 levels (transparent wrappers not counted)."""
    if depth > 6 or not isinstance(node, (dict, list)):
        return None
    if isinstance(node, dict):
        if match(node):
            return node
        tr = _transparent(node)
        for v in node.values():
            r = _find_gate(v, match, depth if tr else depth + 1, flat=tr)
            if r is not None:
                return r
    else:
        for v in node:
            r = _find_gate(v, match, depth if flat else depth + 1)
            if r is not None:
                return r
    return None


def _is_reflexive_node(node: dict) -> bool:
    return any(k.startswith("_") and is_reflexive(v) for k, v in node.items())


def _parse_cost(rule_args: Any) -> Optional[dict]:
    cost: dict = {}
    items = rule_args if isinstance(rule_args, list) else [rule_args]
    for a in items:
        if isinstance(a, dict) and "_Cost" in a:
            c = cost_op(a)          # folded upstream costs keep their variant
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
    aw = anchor_word(rule)
    if aw is not None:
        # Upstream `AnchorWord` ("• Abzan — <ability>") gates the inner ability on the
        # word chosen as the permanent entered (April: _Rule If + TheChosenWordWas).
        word, inner = aw
        rec = project_rule(inner, idx)
        rec.raw = rule
        if rec.condition is None:
            rec.condition = {"op": "AnchorWord", "raw": word}
        return rec

    rule_op = rule.get("_Rule", "")
    kind = _rule_kind(rule_op)
    args = rule.get("args")

    trigger = None
    tnode = _find_first(rule, "_Trigger")
    if tnode is not None:
        tnode = core_trigger(tnode)   # upstream `_Trigger: If` wraps [condition, trigger]
        trigger = {"op": tnode["_Trigger"], "raw": tnode.get("args")}

    cost = _parse_cost(args)

    condition = None
    cnode = _find_gate(args, lambda n: "_Condition" in n)
    if cnode is not None:
        condition = {"op": cnode["_Condition"], "raw": cnode.get("args")}

    action_list = _find_action_list(args)
    effects = extract_effects(action_list)
    if condition is None:
        # A reflexive "When you do, ..." body only happens if the step was done
        # (April: If CostWasPaid around a ReflexiveTrigger). Reflexive ops also occur
        # outside action lists (replacement / prevention actions).
        rnode = _find_gate(args, _is_reflexive_node)
        refl = (next(v for k, v in rnode.items() if k.startswith("_") and is_reflexive(v))
                if rnode is not None else
                next((e.verb for e in effects if is_reflexive(e.verb)), None))
        if refl is not None:
            condition = {"op": refl, "raw": None}
    # The ability as a whole is optional ("you may …") when it has effects and
    # all of them are optional — covers multi-effect MayAction wrappers, not just
    # single-effect ones.
    optional_ability = bool(effects) and all(e.optional for e in effects)

    return AbilityRecord(
        ability_idx=idx, kind=kind, trigger=trigger, cost=cost,
        condition=condition, optional=optional_ability,
        effects=effects, raw=rule,
    )


def project_card(card: dict) -> list[AbilityRecord]:
    """Project a full MTGish card into ability records (one per top-level Rule)."""
    rules = card.get("Rules") or []
    return [project_rule(r, i) for i, r in enumerate(rules) if isinstance(r, dict)]
