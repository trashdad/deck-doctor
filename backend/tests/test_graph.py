"""SP9 deck graph endpoint tests.

SCAFFOLD — remove the skip and implement per roadmap §9.3.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

pytestmark = pytest.mark.skip(reason="SP9 scaffold — implement per roadmap §9.3")


def test_graph_nodes_match_deck():
    """N resolvable ids → exactly N nodes; every category valid (incl. 'commander' for the
    commander node); every edge endpoint is a node id; a < b on every edge."""


def test_graph_thresholds():
    """synergy edges weight >= 0.30; cooccurrence edges weight >= lift_to_norm(2.0);
    combo edges weight == 1.0."""


def test_graph_combo_edges():
    """With the SP7 fixture: deck containing a complete combo yields kind=='combo' edges
    among all member pairs."""


def test_graph_degree_cap():
    """No node participates in more than 12 edges (soft cap 8 — see graph.py docstring
    for why 12 is the hard bound)."""
