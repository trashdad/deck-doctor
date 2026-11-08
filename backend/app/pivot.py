"""Commander pivot finder: which other commanders would this 99 fit better?

Given the working deck (its cards, optionally the current commander) rank
alternative commanders by how well the deck's cards match each candidate's
EDHREC page — the same `edhrec_metrics` (synergy, inclusion) the suggester reads.

Signals, all from data already in the Store (nothing is inferred or invented):

* coverage       — share of the deck's cards that appear on the candidate's EDHREC
                   page at all ("N of your M cards appear on X's page").
* inclusion      — mean EDHREC inclusion rate over the deck (misses count as 0),
                   i.e. how much of this deck the candidate's decks actually run.
* synergy        — mean EDHREC synergy over the cards that DO appear (can be
                   negative: EDHREC synergy is inclusion minus the baseline).
* off-colour     — deck cards whose colour identity is outside the candidate's;
                   each would have to be cut, so it is a penalty and is listed.

score = W_COVERAGE*coverage + W_INCLUSION*inclusion + W_SYNERGY*max(0, synergy)
        - W_OFF_COLOR*(off_color / deck_size)

Candidates come from the Store's commander list (legendary creatures +
planeswalkers, the repo's existing `is_commander` rule), minus the banlist, the
current commander and anything WITHOUT an EDHREC page (no page → no evidence →
omitted, never guessed). Basic lands are ignored on the deck side: they carry no
commander signal. Partner / background pairs are not modelled (v1 — single
commander only).
"""

from __future__ import annotations

from pydantic import BaseModel

from .models import Card
from .suggest import BANLIST, is_commander

W_COVERAGE = 0.5
W_INCLUSION = 0.3
W_SYNERGY = 0.2
W_OFF_COLOR = 1.0

OFF_COLOR_NAMES_SHOWN = 8


class PivotEvidence(BaseModel):
    signal: str   # coverage | edhrec_inclusion | edhrec_synergy | off_color | popularity
    value: float
    detail: str


class PivotMetrics(BaseModel):
    hits: int                 # deck cards on the commander's EDHREC page
    page_size: int            # cards on that EDHREC page (upper bound on hits)
    coverage: float           # hits / deck_size
    inclusion_mean: float     # mean inclusion over the whole deck (miss = 0)
    synergy_mean: float | None  # mean synergy over hits; None when hits == 0
    off_color_count: int
    score: float


class PivotCandidate(BaseModel):
    commander: Card
    in_identity: bool
    off_color_names: list[str]
    deck_count: int
    better_than_current: bool | None  # None when the current commander has no page
    metrics: PivotMetrics
    reason: str
    evidence: list[PivotEvidence]


class PivotCurrent(BaseModel):
    commander: Card
    metrics: PivotMetrics | None  # None when it has no EDHREC page


class PivotResponse(BaseModel):
    deck_size: int                # distinct, resolvable, non-basic deck cards scored
    deck_identity: list[str]      # union colour identity of those cards (WUBRG order)
    current: PivotCurrent | None
    candidates: list[PivotCandidate]


_WUBRG = "WUBRG"


def _sorted_identity(ci: set[str]) -> list[str]:
    return [c for c in _WUBRG if c in ci]


def _is_basic(card: dict) -> bool:
    return "Basic" in (card.get("type_line") or "")


def _deck_cards(store, deck_ids: list[str], exclude: set[str]) -> list[dict]:
    """Distinct resolvable non-basic cards, in first-seen order."""
    seen: set[str] = set()
    out: list[dict] = []
    for cid in deck_ids:
        if cid in seen or cid in exclude:
            continue
        seen.add(cid)
        card = store.get(cid)
        if card is None or _is_basic(card):
            continue
        out.append(card)
    return out


def score_commander(edh: dict[str, tuple[float, float]], deck: list[dict],
                    commander_ci: set[str]) -> tuple[PivotMetrics, list[str]]:
    """Pure scoring of one commander against the deck. Returns (metrics, off-colour names).

    `edh` is the commander's EDHREC page {card_id: (synergy, inclusion)}; an empty
    page scores 0 everywhere (callers omit such commanders — no evidence).
    """
    n = len(deck)
    hits = 0
    inc_sum = 0.0
    syn_sum = 0.0
    off: list[str] = []
    for card in deck:
        row = edh.get(card["id"])
        if row is not None:
            hits += 1
            syn_sum += row[0] or 0.0
            inc_sum += row[1] or 0.0
        if not set(card.get("color_identity") or []) <= commander_ci:
            off.append(card["name"])
    coverage = hits / n if n else 0.0
    inclusion = inc_sum / n if n else 0.0
    synergy = (syn_sum / hits) if hits else None
    off_frac = len(off) / n if n else 0.0
    score = (W_COVERAGE * coverage + W_INCLUSION * inclusion
             + W_SYNERGY * max(0.0, synergy or 0.0) - W_OFF_COLOR * off_frac)
    metrics = PivotMetrics(
        hits=hits, page_size=len(edh), coverage=round(coverage, 4),
        inclusion_mean=round(inclusion, 4),
        synergy_mean=None if synergy is None else round(synergy, 4),
        off_color_count=len(off), score=round(score, 4),
    )
    return metrics, off


def _evidence(name: str, m: PivotMetrics, deck_size: int, off: list[str],
              commander_ci: set[str], deck_count: int) -> tuple[str, list[PivotEvidence]]:
    """Reason sentence + evidence rows. Every clause is backed by a number we computed."""
    ev: list[PivotEvidence] = []
    clauses: list[str] = []

    ev.append(PivotEvidence(
        signal="coverage", value=m.coverage,
        detail=f"{m.hits} of your {deck_size} cards appear on {name}'s EDHREC page "
               f"({m.page_size} cards listed)"))
    clauses.append(f"{m.hits} of your {deck_size} cards appear on {name}'s EDHREC page")

    if m.hits:
        ev.append(PivotEvidence(
            signal="edhrec_inclusion", value=m.inclusion_mean,
            detail=f"mean EDHREC inclusion across your deck {m.inclusion_mean:.0%}"))
        clauses.append(f"mean inclusion {m.inclusion_mean:.0%}")
        if m.synergy_mean is not None:
            ev.append(PivotEvidence(
                signal="edhrec_synergy", value=m.synergy_mean,
                detail=f"mean EDHREC synergy over those {m.hits} cards {m.synergy_mean:+.2f}"))
            clauses.append(f"mean synergy {m.synergy_mean:+.2f}")

    sentence = "; ".join(clauses) + "."
    if off:
        ident = "".join(_sorted_identity(commander_ci)) or "colorless"
        shown = ", ".join(off[:OFF_COLOR_NAMES_SHOWN])
        more = f" (+{len(off) - OFF_COLOR_NAMES_SHOWN} more)" if len(off) > OFF_COLOR_NAMES_SHOWN else ""
        ev.append(PivotEvidence(
            signal="off_color", value=float(len(off)),
            detail=f"{len(off)} cards fall outside its {ident} identity: {shown}{more}"))
        sentence += f" {len(off)} of your cards would have to go (outside {ident}): {shown}{more}."
    if deck_count > 0:
        ev.append(PivotEvidence(
            signal="popularity", value=float(deck_count),
            detail=f"leads {deck_count} decks in the scraped corpus"))
    return sentence, ev


def find_pivots(store, commander_id: str | None, deck_ids: list[str],
                limit: int = 10, max_off_color: int = 8,
                include_all: bool = False) -> dict:
    """Rank alternative commanders for the deck. See module docstring.

    * `max_off_color` — skip candidates that would force more than this many cuts.
    * `include_all`   — also return candidates scoring no better than the current
                        commander (default: only improvements).
    """
    exclude = {commander_id} if commander_id else set()
    deck = _deck_cards(store, deck_ids, exclude)
    deck_size = len(deck)
    deck_ci: set[str] = set()
    for card in deck:
        deck_ci |= set(card.get("color_identity") or [])

    current: dict | None = None
    current_score: float | None = None
    if commander_id:
        cmd = store.get(commander_id)
        if cmd is not None:
            cmd_edh = store.edhrec_for(commander_id)
            cur_metrics = None
            if cmd_edh and deck_size:
                cur_metrics, _ = score_commander(
                    cmd_edh, deck, set(cmd.get("color_identity") or []))
                current_score = cur_metrics.score
            current = {"commander": cmd, "metrics": cur_metrics}

    candidates: list[dict] = []
    if deck_size:
        for cand in store.commanders(limit=0):
            cid = cand["id"]
            if cid in exclude or cand.get("name") in BANLIST or not is_commander(cand):
                continue
            edh = store.edhrec_for(cid)
            if not edh:
                continue  # no EDHREC page → no evidence → omitted
            ci = set(cand.get("color_identity") or [])
            metrics, off = score_commander(edh, deck, ci)
            if len(off) > max_off_color:
                continue
            better = None if current_score is None else metrics.score > current_score
            if better is False and not include_all:
                continue
            deck_count = int(cand.get("deck_count") or 0)
            reason, evidence = _evidence(cand["name"], metrics, deck_size, off, ci, deck_count)
            candidates.append({
                "commander": cand, "in_identity": not off,
                "off_color_names": off[:OFF_COLOR_NAMES_SHOWN],
                "deck_count": deck_count, "better_than_current": better,
                "metrics": metrics, "reason": reason, "evidence": evidence,
            })
    candidates.sort(key=lambda c: (-c["metrics"].score, -c["metrics"].hits,
                                   -c["deck_count"], c["commander"].get("name", "")))
    return {
        "deck_size": deck_size,
        "deck_identity": _sorted_identity(deck_ci),
        "current": current,
        "candidates": candidates[:limit],
    }
