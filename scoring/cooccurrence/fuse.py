"""The fusion seam SP1 documented but did not implement.

fuse() blends SP1's structural synergy with the SP3 co-occurrence signals using a
"fill the remaining headroom" form so identity-when-empty is EXACT (no re-squashing
of the already-[0,1] structural value):

    fuse = 1 - (1 - structural) * exp(-(alpha*lift_norm + beta*edhrec))

With no co-occurrence data (lift_norm = edhrec = 0) -> exp(0) = 1 -> fuse = structural,
bit-for-bit. More signal only raises the score toward 1; output stays in [structural, 1).
Weights are hand-tuned constants (non-goal: learned weights).
"""

from __future__ import annotations

import math
import sys

_MAX_NORM = 1.0 - sys.float_info.epsilon  # codomain upper bound: strictly < 1

LIFT_K = 0.5     # lift squash steepness
ALPHA = 0.6      # weight on symmetric raw-deck lift
BETA = 0.4       # weight on directional EDHREC synergy


def lift_to_norm(lift: float, k: float = LIFT_K) -> float:
    """Map raw lift in [0, inf) to [0, 1): 0 when lift<=1 (no positive association)."""
    if lift <= 1.0:
        return 0.0
    raw = 1.0 - math.exp(-k * (lift - 1.0))
    # Clamp before rounding: large lift underflows exp to 0.0, making raw == 1.0
    raw = min(raw, _MAX_NORM)
    rounded = round(raw, 6)
    return raw if rounded >= 1.0 else rounded


def fuse(structural: float, lift_norm: float, edhrec: float,
         alpha: float = ALPHA, beta: float = BETA) -> float:
    """Fuse structural synergy with co-occurrence signals (see module docstring)."""
    boost = alpha * lift_norm + beta * edhrec
    if boost <= 0.0:
        return round(structural, 6)
    return round(1.0 - (1.0 - structural) * math.exp(-boost), 6)
