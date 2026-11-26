"""Every gate: one passing case and mutation-style negatives (break one thing, expect
exactly that gate to fire)."""

from __future__ import annotations

import copy

import pytest

from card_update import gates
from card_update.config import GatesSection
from card_update.gates import GateInputs, StoreSnapshot, evaluate_all

CFG = GatesSection(min_cards=5, sentinels=["Sol Ring", "Command Tower"], max_unmapped_operators=10)


def _card(i: int, name: str | None = None, **over) -> dict:
    c = {"id": f"id{i}", "oracle_id": f"o{i}", "name": name or f"Card {i}", "type_line": "Artifact",
         "color_identity": [], "cmc": 1.0, "set": "abc", "oracle_text": f"text {i}"}
    c.update(over)
    return c


def _cards(n: int = 10) -> list[dict]:
    out = [_card(i) for i in range(n)]
    out[0]["name"] = "Sol Ring"
    out[1]["name"] = "Command Tower"
    out[1]["type_line"] = "Land"
    return out


def _store(cards: list[dict], untagged: set[str] = frozenset(), ier_over: dict | None = None,
           integrity: str = "ok", tables: dict | None = None) -> StoreSnapshot:
    ids = frozenset(c["id"] for c in cards)
    ier = {c["id"]: float(len(c["name"])) for c in cards}
    ier.update(ier_over or {})
    counts = {t: len(cards) for t in CFG.required_tables}
    counts.update(tables or {})
    return StoreSnapshot(integrity=integrity, table_counts=counts, card_ids=ids,
                         tagged_ids=frozenset(ids - set(untagged)), ier=ier)


def _inputs(**over) -> GateInputs:
    cur = _cards()
    cand = copy.deepcopy(cur)
    base = dict(current_cards=cur, candidate_cards=cand, current_store=_store(cur),
                candidate_store=_store(cand), unmapped=[("Foo", 3)],
                land_meta={"id1": {"name": "Command Tower", "produced_mana": ["C"], "usd": 0.2}})
    base.update(over)
    return GateInputs(**base)


def _fired(results) -> set[str]:
    return {r.gate for r in results if r.violations}


def test_identical_candidate_passes_every_gate():
    results = evaluate_all(_inputs(), CFG)
    assert _fired(results) == set()
    names = {r.gate for r in results}
    assert {"card_schema", "uniqueness", "card_count", "id_stability", "sentinels", "tag_share",
            "lost_all_tags", "unmapped_operators", "ier_stability", "store_integrity",
            "land_meta_coverage"} <= names


def test_metrics_are_reported_with_numbers():
    results = {r.gate: r for r in evaluate_all(_inputs(), CFG)}
    assert results["card_count"].metrics["candidate"] == 10
    assert results["tag_share"].metrics["candidate_pct"] == 100.0
    assert results["ier_stability"].metrics["unchanged_cards"] == 10


# ── card schema / parse ──────────────────────────────────────────────────────

def test_unparseable_cards_fail_schema_and_skip_dependent_gates():
    results = evaluate_all(_inputs(candidate_cards=None, candidate_parse_error="Expecting value"), CFG)
    assert "card_schema" in _fired(results)


@pytest.mark.parametrize("mutate", [
    lambda c: c.pop("oracle_id"),
    lambda c: c.update(name=""),
    lambda c: c.update(cmc=None),
    lambda c: c.update(cmc="1"),
    lambda c: c.update(color_identity="G"),
    lambda c: c.pop("type_line"),
])
def test_missing_or_bad_required_field_fails_schema(mutate):
    inp = _inputs()
    mutate(inp.candidate_cards[4])
    assert "card_schema" in _fired(evaluate_all(inp, CFG))


def test_non_list_cards_fail_schema():
    assert "card_schema" in _fired(evaluate_all(_inputs(candidate_cards={"data": []}), CFG))


# ── uniqueness ──────────────────────────────────────────────────────────────

def test_duplicate_id_fails():
    inp = _inputs()
    inp.candidate_cards[5]["id"] = inp.candidate_cards[6]["id"]
    assert "uniqueness" in _fired(evaluate_all(inp, CFG))


def test_duplicate_oracle_id_fails():
    inp = _inputs()
    inp.candidate_cards[5]["oracle_id"] = inp.candidate_cards[6]["oracle_id"]
    assert "uniqueness" in _fired(evaluate_all(inp, CFG))


# ── count ───────────────────────────────────────────────────────────────────

def test_count_drop_below_ratio_fails():
    r = gates.gate_card_count(98, 100, GatesSection(min_cards=1))
    assert r.violations and r.metrics["ratio"] == 0.98


def test_count_at_exact_ratio_passes():
    assert not gates.gate_card_count(99, 100, GatesSection(min_cards=1)).violations
    assert not gates.gate_card_count(125, 100, GatesSection(min_cards=1)).violations


def test_count_growth_above_ratio_fails():
    assert gates.gate_card_count(126, 100, GatesSection(min_cards=1)).violations


def test_count_below_absolute_floor_fails():
    assert gates.gate_card_count(100, 100, GatesSection(min_cards=101)).violations


# ── id stability ─────────────────────────────────────────────────────────────

def test_changed_id_for_surviving_oracle_fails():
    inp = _inputs()
    inp.candidate_cards[3]["id"] = "reprint-id"
    r = gates.gate_id_stability(inp.current_cards, inp.candidate_cards)
    assert r.violations and r.metrics["changed"] == 1


def test_removed_oracle_and_new_cards_do_not_break_id_stability():
    inp = _inputs()
    del inp.candidate_cards[9]
    inp.candidate_cards.append(_card(99))
    r = gates.gate_id_stability(inp.current_cards, inp.candidate_cards)
    assert not r.violations and r.metrics["kept"] == 9


# ── sentinels ───────────────────────────────────────────────────────────────

def test_missing_sentinel_fails():
    inp = _inputs()
    inp.candidate_cards[1]["name"] = "Command Towr"
    r = gates.gate_sentinels(inp.candidate_cards, CFG.sentinels)
    assert r.violations and r.metrics["missing"] == ["Command Tower"]


# ── tags ────────────────────────────────────────────────────────────────────

def test_tag_share_drop_over_threshold_fails():
    cur = _cards(100)
    cand = copy.deepcopy(cur)
    r = gates.gate_tag_share(_store(cur), _store(cand, untagged={"id10", "id11", "id12"}), 2.0)
    assert r.violations and r.metrics["drop_pp"] == 3.0


def test_tag_share_drop_within_threshold_passes():
    cur = _cards(100)
    r = gates.gate_tag_share(_store(cur), _store(cur, untagged={"id10", "id11"}), 2.0)
    assert not r.violations


def test_previously_tagged_cards_losing_all_tags_fails():
    cur = _cards(100)
    r = gates.gate_lost_all_tags(_store(cur), _store(cur, untagged={"id10", "id11"}), 0.01)
    assert r.violations and r.metrics["lost"] == 2


def test_one_percent_lost_tags_is_allowed():
    cur = _cards(100)
    assert not gates.gate_lost_all_tags(_store(cur), _store(cur, untagged={"id10"}), 0.01).violations


def test_removed_cards_do_not_count_as_lost_tags():
    cur = _cards(100)
    cand = cur[:-5]
    assert not gates.gate_lost_all_tags(_store(cur), _store(cand), 0.01).violations


# ── unmapped operators ──────────────────────────────────────────────────────

BASE = frozenset(f"Op{i}" for i in range(100))


def _ops(names) -> list[tuple[str, int]]:
    return [(n, 1) for n in names]


def test_a_few_new_operators_only_warn():
    r = gates.gate_unmapped(_ops(list(BASE) + ["NewA", "NewB"]), BASE, max_new=40, max_total=3000)
    assert not r.violations and r.metrics["new"] == 2 and r.warnings


def test_a_huge_jump_of_new_operators_fails():
    r = gates.gate_unmapped(_ops(list(BASE) + [f"New{i}" for i in range(41)]), BASE, max_new=40, max_total=3000)
    assert r.violations and r.metrics["new"] == 41


def test_first_run_without_baseline_records_instead_of_failing():
    r = gates.gate_unmapped(_ops([f"Op{i}" for i in range(1500)]), None, max_new=40, max_total=3000)
    assert not r.violations and r.metrics["baseline"] is None and "recording" in r.warnings[0]


def test_absolute_ceiling_still_applies():
    r = gates.gate_unmapped(_ops([f"Op{i}" for i in range(11)]), None, max_new=40, max_total=10)
    assert r.violations and r.metrics["distinct"] == 11


def test_removed_operators_are_fine():
    assert not gates.gate_unmapped(_ops(list(BASE)[:50]), BASE, max_new=0, max_total=3000).violations


def test_unknown_unmapped_count_fails_closed():
    assert gates.gate_unmapped(None, BASE, 40, 3000).violations


# ── IER stability ───────────────────────────────────────────────────────────

def test_ier_change_for_unchanged_card_fails():
    inp = _inputs()
    inp = _inputs(candidate_store=_store(inp.candidate_cards, ier_over={"id4": 123.0}))
    r = {x.gate: x for x in evaluate_all(inp, CFG)}["ier_stability"]
    assert r.violations and r.metrics["ier_changed_unchanged"] == 1


def test_ier_drift_after_a_scoring_code_change_only_warns():
    inp = _inputs()
    inp = _inputs(candidate_store=_store(inp.candidate_cards, ier_over={"id4": 123.0}),
                  ier_enforced=False, ier_note="scoring code changed")
    r = {x.gate: x for x in evaluate_all(inp, CFG)}["ier_stability"]
    assert not r.violations and r.metrics["enforced"] is False
    assert "1 unchanged card(s) changed IER" in r.warnings[0]


def test_ier_change_for_changed_card_is_reported_not_failed():
    inp = _inputs()
    inp.candidate_cards[4]["oracle_text"] = "errata"
    inp.candidate_store = _store(inp.candidate_cards, ier_over={"id4": 123.0})
    r = {x.gate: x for x in evaluate_all(inp, CFG)}["ier_stability"]
    assert not r.violations
    assert r.metrics["changed_cards"] == 1 and r.metrics["ier_changed_changed_cards"] == 1


def test_cards_missing_from_the_current_store_are_not_comparable():
    inp = _inputs()
    stale = _store(inp.current_cards[:8])
    r = gates.gate_ier_stability(inp.current_cards, inp.candidate_cards, stale,
                                 inp.candidate_store, 0)
    assert not r.violations and r.metrics["not_comparable"] == 2


# ── store integrity ─────────────────────────────────────────────────────────

IDS = frozenset(c["id"] for c in _cards())


def test_store_matching_cards_passes():
    assert not gates.gate_store_integrity(_store(_cards()), CFG.required_tables, IDS).violations


def test_integrity_check_failure_fails():
    assert gates.gate_store_integrity(_store(_cards(), integrity="*** page 3 corrupt"),
                                      CFG.required_tables, IDS).violations


def test_empty_required_table_fails():
    st = _store(_cards(), tables={"card_flat_tags": 0})
    assert gates.gate_store_integrity(st, CFG.required_tables, IDS).violations


def test_missing_required_table_fails():
    st = _store(_cards())
    counts = dict(st.table_counts)
    counts.pop("synergies")
    st = StoreSnapshot(st.integrity, counts, st.card_ids, st.tagged_ids, st.ier)
    assert gates.gate_store_integrity(st, CFG.required_tables, IDS).violations


def test_same_count_but_different_ids_fails():
    cards = _cards()
    stale = [dict(c) for c in cards]
    stale[3]["id"] = "stale-id"                  # same row count, one wrong id
    r = gates.gate_store_integrity(_store(stale), CFG.required_tables, IDS)
    assert r.violations and r.metrics["missing_ids"] == 1 and r.metrics["extra_ids"] == 1


def test_card_without_ier_fails():
    r = gates.gate_store_integrity(_store(_cards(), ier_over={"id2": None}), CFG.required_tables, IDS)
    assert r.violations and r.metrics["null_ier"] == 1


# ── land meta ───────────────────────────────────────────────────────────────

def test_land_meta_missing_lands_fails():
    r = gates.gate_land_meta({}, _cards(), 0.99)
    assert r.violations and r.metrics["lands"] == 1


def test_land_meta_skipped_when_enrich_disabled():
    r = gates.gate_land_meta(None, _cards(), 0.99)
    assert not r.violations and r.metrics["skipped"] is True


# ── real default thresholds on realistic-shaped data (2026-11 rehearsal numbers) ──

def _realistic(n_cur: int = 31_946, n_new: int = 529, tagged_share: float = 0.879, n_ops: int = 1_454):
    from card_update.config import GatesSection as G
    cur = [_card(i) for i in range(n_cur)]
    names = ["Sol Ring", "Arcane Signet", "Command Tower", "Birds of Paradise", "Cultivate",
             "Swords to Plowshares", "Rhystic Study"]
    for i, nm in enumerate(names):
        cur[i]["name"] = nm
    for c in cur[: n_cur // 25]:
        c["type_line"] = "Land"
    cand = [dict(c) for c in cur] + [_card(n_cur + i) for i in range(n_new)]
    untagged_cur = {c["id"] for c in cur[int(n_cur * tagged_share):]}
    untagged_cand = untagged_cur | {c["id"] for c in cand[n_cur + int(n_new * tagged_share):]}
    base_ops = frozenset(f"Op{i}" for i in range(n_ops))
    land = {c["id"]: {"name": c["name"], "produced_mana": ["G"], "usd": 1.0}
            for c in cand if c["type_line"] == "Land"}
    inp = GateInputs(current_cards=cur, candidate_cards=cand, current_store=_store(cur, untagged_cur),
                     candidate_store=_store(cand, untagged_cand), unmapped=_ops(list(base_ops) + [f"N{i}" for i in range(15)]),
                     land_meta=land, unmapped_baseline=base_ops)
    return inp, G()


def test_default_thresholds_pass_a_realistic_new_set():
    inp, cfg = _realistic()
    assert _fired(evaluate_all(inp, cfg)) == set()


def test_default_thresholds_catch_a_two_percent_card_loss():
    inp, cfg = _realistic()
    inp.candidate_cards = inp.candidate_cards[: int(len(inp.current_cards) * 0.98)]
    inp.candidate_store = _store(inp.candidate_cards)
    assert "card_count" in _fired(evaluate_all(inp, cfg))


def test_default_thresholds_catch_a_tag_collapse():
    inp, cfg = _realistic()
    ids = [c["id"] for c in inp.candidate_cards]
    already = inp.candidate_store.card_ids - inp.candidate_store.tagged_ids
    inp.candidate_store = _store(inp.candidate_cards, untagged=set(already) | set(ids[: len(ids) // 10]))
    fired = _fired(evaluate_all(inp, cfg))
    assert {"tag_share", "lost_all_tags"} <= fired


def test_default_thresholds_catch_an_mtgish_schema_break():
    inp, cfg = _realistic()
    inp.unmapped = _ops([f"Renamed{i}" for i in range(1_454)])
    assert "unmapped_operators" in _fired(evaluate_all(inp, cfg))
