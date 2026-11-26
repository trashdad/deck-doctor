"""Quality gates for a candidate card layer. Pure functions: data in, GateResult out.

Each gate returns its metrics (always, so the log shows the numbers) and a list of
violations. Any violation aborts the run before promote. Thresholds come from
``config.GatesSection``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from card_update.config import GatesSection

_EXAMPLES = 5


@dataclass(frozen=True)
class Violation:
    gate: str
    message: str


@dataclass
class GateResult:
    gate: str
    metrics: dict[str, Any] = field(default_factory=dict)
    violations: list[Violation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)      # logged loudly, never block

    def fail(self, message: str) -> None:
        self.violations.append(Violation(self.gate, message))


@dataclass(frozen=True)
class StoreSnapshot:
    integrity: str                         # "ok" or the integrity_check output ("" = not checked)
    table_counts: Mapping[str, int]
    card_ids: frozenset[str]               # ids in the store's `cards` table
    tagged_ids: frozenset[str]             # ids with a non-empty card_flat_tags row
    ier: Mapping[str, float | None]


@dataclass
class GateInputs:
    current_cards: list[dict]
    candidate_cards: Any                   # whatever the candidate cards.json parsed to (None = unparseable)
    current_store: StoreSnapshot
    candidate_store: StoreSnapshot
    unmapped: list[tuple[str, int]] | None
    land_meta: dict[str, Any] | None       # None = enrich stage disabled
    candidate_parse_error: str | None = None
    unmapped_baseline: frozenset[str] | None = None   # operators unmapped in the live release (None = first run)
    ier_enforced: bool = True              # False after a scoring-code change (fingerprint.py)
    ier_note: str = ""


def _examples(items: Iterable[Any]) -> list[Any]:
    out = []
    for i, x in enumerate(items):
        if i >= _EXAMPLES:
            break
        out.append(x)
    return out


def _pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 3) if d else 0.0


# ── card-file gates ──────────────────────────────────────────────────────────

def _field_problem(card: dict, fld: str) -> str | None:
    if fld not in card or card[fld] is None:
        return "missing"
    v = card[fld]
    if fld in ("id", "name", "oracle_id") and (not isinstance(v, str) or not v.strip()):
        return "empty"
    if fld == "type_line" and not isinstance(v, str):
        return "not a string"
    if fld == "color_identity" and not isinstance(v, list):
        return "not a list"
    if fld == "cmc" and (isinstance(v, bool) or not isinstance(v, (int, float))):
        return "not a number"
    return None


def gate_card_schema(cards: Any, required: list[str], parse_error: str | None = None) -> GateResult:
    r = GateResult("card_schema")
    if parse_error is not None or cards is None:
        r.fail(f"candidate cards.json does not parse: {parse_error or 'no data'}")
        return r
    if not isinstance(cards, list):
        r.fail(f"candidate cards.json must be a JSON array, got {type(cards).__name__}")
        return r
    bad: list[str] = []
    for i, c in enumerate(cards):
        if not isinstance(c, dict):
            bad.append(f"#{i}: not an object")
            continue
        for fld in required:
            prob = _field_problem(c, fld)
            if prob:
                bad.append(f"{c.get('name') or c.get('id') or f'#{i}'}: {fld} {prob}")
    r.metrics.update(cards=len(cards), bad_fields=len(bad))
    if bad:
        r.fail(f"{len(bad)} card field problem(s), e.g. {_examples(bad)}")
    return r


def gate_uniqueness(cards: list[dict]) -> GateResult:
    r = GateResult("uniqueness")
    for key in ("id", "oracle_id"):
        dupes = [k for k, n in Counter(c.get(key) for c in cards).items() if n > 1]
        r.metrics[f"duplicate_{key}s"] = len(dupes)
        if dupes:
            r.fail(f"{len(dupes)} duplicate {key}(s), e.g. {_examples(dupes)}")
    return r


def gate_card_count(n_candidate: int, n_current: int, cfg: GatesSection) -> GateResult:
    r = GateResult("card_count")
    ratio = round(n_candidate / n_current, 4) if n_current else float("inf")
    r.metrics.update(candidate=n_candidate, current=n_current, ratio=ratio,
                     min_ratio=cfg.min_count_ratio, max_ratio=cfg.max_count_ratio,
                     floor=cfg.min_cards)
    if n_candidate < cfg.min_cards:
        r.fail(f"{n_candidate:,} cards is below the absolute floor of {cfg.min_cards:,}")
    if n_current and n_candidate < cfg.min_count_ratio * n_current:
        r.fail(f"card count fell to {n_candidate:,} ({ratio:.2%} of {n_current:,}); "
               f"minimum is {cfg.min_count_ratio:.0%}")
    if n_current and n_candidate > cfg.max_count_ratio * n_current:
        r.fail(f"card count jumped to {n_candidate:,} ({ratio:.2%} of {n_current:,}); "
               f"maximum is {cfg.max_count_ratio:.0%}")
    return r


def gate_id_stability(current: list[dict], candidate: list[dict]) -> GateResult:
    """Every previous card whose oracle_id survives must keep its id (user decks store ids)."""
    r = GateResult("id_stability")
    prev = {c["oracle_id"]: c for c in current}
    changed = [(prev[c["oracle_id"]]["name"], prev[c["oracle_id"]]["id"], c["id"])
               for c in candidate if c["oracle_id"] in prev and prev[c["oracle_id"]]["id"] != c["id"]]
    surviving = sum(1 for c in candidate if c["oracle_id"] in prev)
    r.metrics.update(surviving_oracles=surviving, kept=surviving - len(changed), changed=len(changed))
    if changed:
        r.fail(f"{len(changed)} surviving card(s) changed id (would orphan user decks), "
               f"e.g. {_examples(changed)}")
    return r


def gate_sentinels(candidate: list[dict], sentinels: list[str]) -> GateResult:
    r = GateResult("sentinels")
    names = {c.get("name") for c in candidate}
    missing = [s for s in sentinels if s not in names]
    r.metrics.update(checked=len(sentinels), missing=missing)
    if missing:
        r.fail(f"sentinel card(s) missing: {missing}")
    return r


# ── store gates ─────────────────────────────────────────────────────────────

def _tag_share(store: StoreSnapshot) -> float:
    return _pct(len(store.tagged_ids & store.card_ids), len(store.card_ids))


def gate_tag_share(current: StoreSnapshot, candidate: StoreSnapshot, max_drop_pp: float) -> GateResult:
    r = GateResult("tag_share")
    cur, cand = _tag_share(current), _tag_share(candidate)
    drop = round(cur - cand, 3)
    r.metrics.update(current_pct=cur, candidate_pct=cand, drop_pp=drop, max_drop_pp=max_drop_pp)
    if drop > max_drop_pp:
        r.fail(f"share of cards with tags fell {drop:.2f} pp ({cur:.2f}% -> {cand:.2f}%); "
               f"max allowed drop is {max_drop_pp:.2f} pp")
    return r


def gate_lost_all_tags(current: StoreSnapshot, candidate: StoreSnapshot, max_ratio: float) -> GateResult:
    r = GateResult("lost_all_tags")
    base = current.tagged_ids & candidate.card_ids
    lost = sorted(base - candidate.tagged_ids)
    ratio = len(lost) / len(base) if base else 0.0
    r.metrics.update(previously_tagged=len(base), lost=len(lost), ratio=round(ratio, 5),
                     max_ratio=max_ratio, examples=_examples(lost))
    if ratio > max_ratio:
        r.fail(f"{len(lost):,} of {len(base):,} previously tagged cards ({ratio:.2%}) lost ALL "
               f"tags; max allowed is {max_ratio:.2%}; e.g. {_examples(lost)}")
    return r


def gate_unmapped(unmapped: list[tuple[str, int]] | None, baseline: frozenset[str] | None,
                  max_new: int, max_total: int) -> GateResult:
    """NEW unmapped operators vs the live release's recorded set, plus an absolute ceiling.
    Without a recorded set (first run) only the ceiling applies and this run's set becomes
    the baseline on promote."""
    r = GateResult("unmapped_operators")
    if unmapped is None:
        r.fail("unmapped-operator report unavailable — cannot judge new MTGish operators")
        return r
    ops = {op for op, _ in unmapped}
    new = sorted(ops - baseline) if baseline is not None else []
    r.metrics.update(distinct=len(ops), occurrences=sum(n for _, n in unmapped),
                     baseline=None if baseline is None else len(baseline), new=len(new),
                     new_examples=_examples(new), max_new=max_new, max_distinct=max_total,
                     top=[f"{op}:{n}" for op, n in unmapped[:10]])
    if baseline is None:
        r.warnings.append(f"no recorded unmapped-operator baseline; recording {len(ops):,} operators "
                          "(only the absolute ceiling applies this run)")
    elif new:
        r.warnings.append(f"{len(new)} new unmapped MTGish operator(s): {new[:20]}")
    if len(ops) > max_total:
        r.fail(f"{len(ops):,} distinct unmapped MTGish operators exceeds the ceiling {max_total:,}")
    if len(new) > max_new:
        r.fail(f"{len(new):,} NEW unmapped MTGish operators (max {max_new}) — upstream changed its "
               f"schema or a big new mechanic needs tag_taxonomy mappings; e.g. {new[:10]}")
    return r


def gate_ier_stability(current_cards: list[dict], candidate_cards: list[dict],
                       current: StoreSnapshot, candidate: StoreSnapshot, max_changed: int,
                       enforce: bool = True, note: str = "") -> GateResult:
    """IER is a pure function of the card and the scoring code: with unchanged code an
    unchanged card must score identically. After a scoring-code change (enforce=False)
    the drift is reported as a warning instead."""
    r = GateResult("ier_stability")
    prev = {c["id"]: c for c in current_cards}
    unchanged = [c["id"] for c in candidate_cards if prev.get(c["id"]) == c]
    changed_cards = [c["id"] for c in candidate_cards if c["id"] in prev and prev[c["id"]] != c]
    comparable = [i for i in unchanged if i in current.ier and i in candidate.ier]
    drift = [i for i in comparable if current.ier[i] != candidate.ier[i]]
    changed_drift = [i for i in changed_cards
                     if i in current.ier and i in candidate.ier and current.ier[i] != candidate.ier[i]]
    r.metrics.update(unchanged_cards=len(unchanged), comparable=len(comparable),
                     not_comparable=len(unchanged) - len(comparable),
                     ier_changed_unchanged=len(drift), changed_cards=len(changed_cards),
                     ier_changed_changed_cards=len(changed_drift), max_changed=max_changed,
                     enforced=enforce)
    if not enforce:
        r.warnings.append(f"IER enforcement skipped: {note}; {len(drift):,} unchanged card(s) changed IER")
        return r
    if len(drift) > max_changed:
        ex = [(i, current.ier[i], candidate.ier[i]) for i in _examples(drift)]
        r.fail(f"IER changed for {len(drift):,} cards whose data did not change (max {max_changed}); "
               f"scoring code or store drifted; e.g. {ex}")
    return r


def gate_store_integrity(store: StoreSnapshot, required_tables: list[str], candidate_ids: frozenset[str]) -> GateResult:
    """integrity_check ok, required tables non-empty, and the store's `cards` rows are
    exactly the candidate cards.json ids, each with an IER."""
    r = GateResult("store_integrity")
    r.metrics.update(integrity=store.integrity,
                     tables={t: store.table_counts.get(t) for t in required_tables})
    if store.integrity != "ok":
        r.fail(f"candidate scores.sqlite integrity_check: {store.integrity[:300]}")
    empty = [t for t in required_tables if not store.table_counts.get(t)]
    if empty:
        r.fail(f"required table(s) missing or empty: {empty}")
    missing = sorted(candidate_ids - store.card_ids)
    extra = sorted(store.card_ids - candidate_ids)
    no_ier = sorted(i for i in candidate_ids & store.card_ids if store.ier.get(i) is None)
    r.metrics.update(missing_ids=len(missing), extra_ids=len(extra), null_ier=len(no_ier))
    if missing or extra:
        r.fail(f"store card ids differ from candidate cards.json: {len(missing):,} missing "
               f"(e.g. {_examples(missing)}), {len(extra):,} extra (e.g. {_examples(extra)})")
    if no_ier:
        r.fail(f"{len(no_ier):,} candidate cards have no IER in the store, e.g. {_examples(no_ier)}")
    return r


def gate_land_meta(land_meta: dict[str, Any] | None, candidate: list[dict], min_coverage: float) -> GateResult:
    r = GateResult("land_meta_coverage")
    if land_meta is None:
        r.metrics["skipped"] = True
        return r
    lands = [c["id"] for c in candidate if "Land" in (c.get("type_line") or "")]
    covered = [i for i in lands if isinstance(land_meta.get(i), dict)]
    cov = len(covered) / len(lands) if lands else 1.0
    r.metrics.update(skipped=False, lands=len(lands), covered=len(covered),
                     coverage=round(cov, 5), min_coverage=min_coverage)
    if cov < min_coverage:
        missing = [i for i in lands if i not in land_meta]
        r.fail(f"land_meta covers {len(covered):,}/{len(lands):,} lands ({cov:.2%}); minimum "
               f"{min_coverage:.0%}; e.g. missing {_examples(missing)}")
    return r


# ── all together ────────────────────────────────────────────────────────────

def evaluate_all(inp: GateInputs, cfg: GatesSection) -> list[GateResult]:
    results = [gate_card_schema(inp.candidate_cards, cfg.required_fields, inp.candidate_parse_error)]
    if results[0].violations:
        return results          # nothing else can be judged on unreadable cards
    cand: list[dict] = inp.candidate_cards
    cur = inp.current_cards
    results.append(gate_uniqueness(cand))
    results.append(gate_card_count(len(cand), len(cur), cfg))
    results.append(gate_id_stability(cur, cand))
    results.append(gate_sentinels(cand, cfg.sentinels))
    results.append(gate_tag_share(inp.current_store, inp.candidate_store, cfg.max_tag_share_drop_pp))
    results.append(gate_lost_all_tags(inp.current_store, inp.candidate_store, cfg.max_lost_all_tags_ratio))
    results.append(gate_unmapped(inp.unmapped, inp.unmapped_baseline, cfg.max_new_unmapped_operators,
                                 cfg.max_unmapped_operators))
    results.append(gate_ier_stability(cur, cand, inp.current_store, inp.candidate_store,
                                      cfg.max_ier_changed_unchanged, inp.ier_enforced, inp.ier_note))
    results.append(gate_store_integrity(inp.candidate_store, cfg.required_tables,
                                        frozenset(c["id"] for c in cand)))
    results.append(gate_land_meta(inp.land_meta, cand, cfg.min_land_meta_coverage))
    return results
