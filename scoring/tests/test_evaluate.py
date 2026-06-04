"""Unit tests for the IER / CSS / DER scoring core."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simmander_scoring.evaluate import (  # noqa: E402
    CSS_MAX,
    IER_MAX,
    IER_MIN,
    combinatorial_synergy_score,
    dynamic_efficiency_ratio,
    has_lift,
    isolated_efficiency_rating,
)
from simmander_scoring.mechanics import tag_card  # noqa: E402

TOKEN_PRODUCER = {
    "id": "a", "cmc": 3, "type_line": "Legendary Creature",
    "oracle_text": "If one or more tokens would be created under your control, "
                   "those tokens plus that many Squirrel creature tokens are created instead.",
}
TOKEN_PAYOFF = {
    "id": "b", "cmc": 5, "type_line": "Enchantment",
    "oracle_text": "If an effect would create one or more tokens under your control, "
                   "it creates twice that many of those tokens instead.",
}
INFECT_A = {"id": "c", "cmc": 12, "type_line": "Artifact Creature",
            "oracle_text": "Trample, infect.", "keywords": ["Infect"], "power": "11", "toughness": "11"}
INFECT_B = {"id": "d", "cmc": 4, "type_line": "Artifact — Equipment",
            "oracle_text": "Equipped creature gets +2/+2 and has infect.", "keywords": ["Infect"]}
VANILLA = {"id": "e", "cmc": 6, "type_line": "Creature — Bear",
           "oracle_text": "", "power": "2", "toughness": "2"}


def test_ier_within_bounds():
    for card in (TOKEN_PRODUCER, TOKEN_PAYOFF, INFECT_A, VANILLA):
        ier = isolated_efficiency_rating(card)
        assert IER_MIN <= ier <= IER_MAX


def test_ier_handles_missing_keys():
    # Doc A requirement: tolerate missing JSON keys gracefully.
    ier = isolated_efficiency_rating({})
    assert IER_MIN <= ier <= IER_MAX


def test_cheap_value_beats_expensive_vanilla():
    cheap_draw = {"id": "x", "cmc": 2, "type_line": "Sorcery",
                  "oracle_text": "Draw two cards."}
    assert isolated_efficiency_rating(cheap_draw) > isolated_efficiency_rating(VANILLA)


def test_css_rewards_complementary_pair():
    css = combinatorial_synergy_score(tag_card(TOKEN_PRODUCER), tag_card(TOKEN_PAYOFF))
    assert css >= 2.0  # exponential territory


def test_css_zero_for_unrelated():
    css = combinatorial_synergy_score(tag_card(TOKEN_PRODUCER), tag_card(VANILLA))
    assert css == 0.0


def test_css_capped():
    css = combinatorial_synergy_score(tag_card(INFECT_A), tag_card(INFECT_A))
    assert css <= CSS_MAX


def test_lift_flag_for_shared_parasitic():
    assert has_lift(tag_card(INFECT_A), tag_card(INFECT_B))
    assert not has_lift(tag_card(INFECT_A), tag_card(VANILLA))


def test_der_formula_matches_doc():
    # Doc A worked example: IER_A=5.6, IER_B=13.1, CSS=0 -> additive 18.7.
    assert dynamic_efficiency_ratio(5.6, 13.1, 0.0) == 18.7
    # With synergy the pair term is IER_A * CSS on top.
    assert dynamic_efficiency_ratio(5.6, 13.1, 2.0) == round(5.6 + 13.1 + 5.6 * 2.0, 2)


def test_der_zero_synergy_is_additive():
    assert dynamic_efficiency_ratio(4.0, 6.0, 0.0) == 10.0
