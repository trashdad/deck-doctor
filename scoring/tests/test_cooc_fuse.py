import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cooccurrence.fuse import lift_to_norm, fuse  # noqa: E402


def test_lift_to_norm_zero_at_or_below_one():
    assert lift_to_norm(1.0) == 0.0
    assert lift_to_norm(0.5) == 0.0
    assert lift_to_norm(3.0) > 0.0
    assert lift_to_norm(10.0) > lift_to_norm(3.0)
    assert lift_to_norm(1e9) < 1.0


def test_fuse_identity_when_no_signal():
    assert fuse(0.0, 0.0, 0.0) == 0.0
    assert fuse(0.42, 0.0, 0.0) == 0.42
    assert fuse(1.0, 0.0, 0.0) == 1.0


def test_fuse_monotonic_and_bounded():
    base = fuse(0.3, 0.0, 0.0)
    more_lift = fuse(0.3, 0.5, 0.0)
    more_edh = fuse(0.3, 0.0, 0.5)
    assert more_lift > base
    assert more_edh > base
    assert base <= more_lift < 1.0
    assert fuse(0.3, 1.0, 1.0) < 1.0
    assert fuse(0.3, 1.0, 1.0) >= 0.3
