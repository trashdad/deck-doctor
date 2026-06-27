"""Card Upgrade Finder — "replace THIS card with a better one that does the same thing".

Given a card already in the deck, surface in-identity replacements that keep the
card's *function* but improve on it along one or more axes the user controls:

  * efficiency  — a tunable slider [0..1]. 0 = "find the closest functional match"
                  (same effect, similar cost), 1 = "maximise efficiency" (biggest
                  IER gain among cards that still do something similar).
  * synergy     — toggle: favour cards with strong EDHREC synergy to the commander.
  * flexibility — toggle: favour *multimodal* upgrades (a card that does the same
                  thing PLUS more — e.g. swap a "-4/-4 to a creature" for a
                  "destroy any permanent, and make a token").

It composes signals that already exist in the Store rather than inventing new
ones: similar_cards() (TF-IDF functional similarity), category_of() (functional
class), ier (efficiency), edhrec_for() (commander synergy), and _suggestable()
(colour-identity + banlist gate).

The ranking math lives in `rank_upgrades`, a PURE function over plain signal
dicts — no Store, no DB — so it is unit-testable in isolation. `find_upgrades`
is the thin orchestrator that pulls signals out of the Store and calls it.
"""

from __future__ import annotations

# Constant blend weights for the axes the slider does NOT control. The slider
# splits the remaining mass between functional similarity and raw efficiency.
W_COST = 0.20            # "about the same cost" always matters a little
SYN_ON, SYN_OFF = 0.60, 0.15
FLEX_ON, FLEX_OFF = 0.50, 0.10
# A candidate must look at least this similar in function to be offered at all,
# unless it shares the target's coarse category (removal -> removal, etc.).
MIN_SIMILARITY = 0.05


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _coverage(target: set[str], cand: set[str]) -> float:
    """Fraction of the TARGET's tags the candidate also has (containment, not Jaccard).

    Coverage — not symmetric Jaccard — is the right metric for a *replacement*: a
    card that does everything the target does PLUS more should count as fully
    similar, not be penalised for its extra tags. That's what lets the flexibility
    toggle promote multimodal upgrades instead of fighting them.
    """
    if not target:
        return 0.0
    return len(target & cand) / len(target)


def _functional_similarity(target: dict, cand: dict) -> float:
    """0..1 blend: how much of the target's function the candidate covers + category."""
    sem = _coverage(set(target["sem"]), set(cand["sem"]))
    mech = _coverage(set(target["mech"]), set(cand["mech"]))
    same_cat = 1.0 if target["category"] == cand["category"] else 0.0
    return round(0.55 * sem + 0.25 * mech + 0.20 * same_cat, 4)


def _flexibility(target: dict, cand: dict) -> float:
    """Multimodal bonus: extra functional roles the candidate has beyond the target."""
    extra = set(cand["mech"]) - set(target["mech"])
    return round(min(1.0, len(extra) / 2.0), 4)


def rank_upgrades(
    target: dict,
    candidates: list[dict],
    *,
    efficiency: float = 0.5,
    favor_synergy: bool = False,
    favor_flexibility: bool = False,
    synergy: dict[str, float] | None = None,
    limit: int = 12,
) -> list[dict]:
    """Rank candidate replacements for `target`. PURE — no Store/DB.

    Each signal dict (target + candidates) must carry:
        id, card, ier (float|None), cmc (float), category (str),
        mech (iterable[str]), sem (iterable[str])
    `synergy` maps candidate id -> commander synergy in [0,1] (default 0).

    Returns option dicts: {card, score, efficiency_gain, similarity, reasons}.
    """
    synergy = synergy or {}
    p = max(0.0, min(1.0, efficiency))
    w_sim = 1.0 - p
    w_eff = p
    w_syn = SYN_ON if favor_synergy else SYN_OFF
    w_flex = FLEX_ON if favor_flexibility else FLEX_OFF
    total_w = w_sim + w_eff + w_syn + w_flex + W_COST

    t_ier = target.get("ier") or 0.0
    t_cmc = float(target.get("cmc") or 0.0)
    t_name = target["card"].get("name", "this card")

    # Pre-compute functional similarity + gate, collect IERs for min-max normalisation.
    rows: list[dict] = []
    for c in candidates:
        if c["id"] == target["id"]:
            continue
        sim = _functional_similarity(target, c)
        same_cat = target["category"] == c["category"]
        if sim < MIN_SIMILARITY and not same_cat:
            continue  # doesn't do anything similar — not a replacement
        rows.append({"c": c, "sim": sim})
    if not rows:
        return []

    iers = [r["c"].get("ier") or 0.0 for r in rows]
    lo, hi = min(iers), max(iers)
    span = (hi - lo) or 1.0

    options: list[dict] = []
    for r in rows:
        c = r["c"]
        sim = r["sim"]
        c_ier = c.get("ier") or 0.0
        eff_norm = (c_ier - lo) / span                # 0..1 within candidate set
        eff_gain = round(c_ier - t_ier, 2)
        syn = max(0.0, min(1.0, synergy.get(c["id"], 0.0)))
        flex = _flexibility(target, c)
        c_cmc = float(c.get("cmc") or 0.0)
        cost_sim = 1.0 - min(1.0, abs(c_cmc - t_cmc) / 4.0)

        score = (w_sim * sim + w_eff * eff_norm + w_syn * syn
                 + w_flex * flex + W_COST * cost_sim) / total_w

        options.append({
            "card": c["card"],
            "score": round(score, 6),
            "efficiency_gain": eff_gain,
            "similarity": sim,
            "reasons": _reasons(t_name, t_cmc, c, sim, eff_gain, syn, flex, c_cmc),
        })

    options.sort(key=lambda o: (-o["score"], -o["efficiency_gain"], o["card"]["name"]))
    return options[:limit]


def _reasons(t_name, t_cmc, cand, sim, eff_gain, syn, flex, c_cmc) -> list[dict]:
    out: list[dict] = []
    if eff_gain > 0.05:
        out.append({"signal": "efficiency", "value": round(eff_gain, 2),
                    "detail": f"+{eff_gain:.1f} IER vs {t_name}"})
    if sim > 0:
        out.append({"signal": "similar", "value": round(sim, 3),
                    "detail": f"does a similar {cand['category'].replace('_', ' ')} job"})
    if syn > 0:
        out.append({"signal": "synergy", "value": round(syn, 3),
                    "detail": "strong EDHREC synergy with your commander"})
    if flex > 0:
        extra = sorted(set(cand["mech"]) - set())  # display candidate's roles
        out.append({"signal": "flexibility", "value": round(flex, 3),
                    "detail": "more flexible — covers extra roles"})
    if c_cmc < t_cmc:
        out.append({"signal": "cost", "value": round(t_cmc - c_cmc, 2),
                    "detail": f"{int(t_cmc - c_cmc)} mana cheaper"})
    return out


def _signal(category_of, card: dict) -> dict:
    """Build a ranking signal dict from an enriched Store card."""
    return {
        "id": card["id"],
        "card": card,
        "ier": card.get("ier"),
        "cmc": card.get("cmc") or 0.0,
        "category": category_of(card),
        "mech": card.get("mechanic_tags") or [],
        "sem": card.get("semantic_tags") or [],
    }


def find_upgrades(store, target_id: str, commander_id: str | None,
                  deck_ids: list[str], *, efficiency: float = 0.5,
                  favor_synergy: bool = False, favor_flexibility: bool = False,
                  limit: int = 12) -> dict:
    """Orchestrator: pull candidate signals from the Store and rank them.

    Candidate pool = the target's functional neighbours (TF-IDF similar_cards),
    gated to the commander's colour identity (or the target's own if no commander),
    excluding the target and cards already in the deck.
    """
    # Lazy imports keep the pure ranking path (rank_upgrades) free of psycopg2.
    from .doctor import category_of
    from .suggest import _suggestable

    target = store.get(target_id)
    if target is None:
        return {"target": None, "options": []}

    ci = set((store.get(commander_id) or {}).get("color_identity") or []) if commander_id else None
    if ci is None:
        ci = set(target.get("color_identity") or [])

    in_deck = set(deck_ids) | {target_id}
    if commander_id:
        in_deck.add(commander_id)

    target_sig = _signal(category_of, target)

    # Functional neighbours (semantic similarity). Pull generously, then filter.
    pool = store.similar_cards(target_id, limit=max(limit * 12, 120))
    cand_sigs: list[dict] = []
    seen: set[str] = set()
    for card in pool:
        cid = card["id"]
        if cid in in_deck or cid in seen:
            continue
        if not _suggestable(card, ci):
            continue
        seen.add(cid)
        cand_sigs.append(_signal(category_of, card))

    edh = store.edhrec_for(commander_id) if commander_id else {}
    synergy = {cid: max(0.0, min(1.0, edh[cid][0])) for cid in edh}

    options = rank_upgrades(
        target_sig, cand_sigs,
        efficiency=efficiency, favor_synergy=favor_synergy,
        favor_flexibility=favor_flexibility, synergy=synergy, limit=limit,
    )
    return {"target": target, "options": options}


def upgrade_sweep(store, commander_id: str, deck_ids: list[str], *,
                  weak: int = 12, per_card: int = 3, max_swaps: int = 10,
                  efficiency: float = 0.4, favor_synergy: bool = True,
                  favor_flexibility: bool = False,
                  _cuts=None, _upgrades=None) -> dict:
    """Deck-wide "tune-up": the weakest cards in the deck, each with replacements.

    This is the precon-cut idea — load a precon, see which cards the data says are
    pulling least weight (low EDHREC/structural synergy with the commander, i.e.
    the cards people typically cut), and for each get a similar-but-better swap.

    Composes two tested pieces: `suggest_cuts` (which cards to cut) and
    `find_upgrades` (what to put in their place). The `_cuts`/`_upgrades` params are
    injection seams for unit tests; production uses the real implementations.
    """
    if _cuts is None:
        from .doctor import suggest_cuts as _cuts  # noqa: PLW0642
    if _upgrades is None:
        _upgrades = find_upgrades

    cuts = _cuts(store, commander_id, deck_ids, limit=weak)
    swaps: list[dict] = []
    for cut in cuts:
        target = store.get(cut["card_id"])
        if target is None:
            continue
        res = _upgrades(
            store, cut["card_id"], commander_id, deck_ids,
            efficiency=efficiency, favor_synergy=favor_synergy,
            favor_flexibility=favor_flexibility, limit=per_card,
        )
        options = res.get("options", [])
        if not options:
            continue  # no better replacement exists — leave the card alone
        swaps.append({
            "target": target,
            "weakness": cut.get("contribution", 0.0),
            "weakness_reasons": cut.get("reasons", []),
            "options": options,
        })
        if len(swaps) >= max_swaps:
            break
    return {"swaps": swaps}
