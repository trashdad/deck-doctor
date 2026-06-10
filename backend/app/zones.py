"""Canonical deck zone order — mirror of frontend/src/lib/zones.ts::ZONES.

Used by the export endpoint (SP6) to group cards in a stable, human-friendly order.
"""

from __future__ import annotations

ZONE_ORDER = [
    "Commanders", "Lands", "Ramp", "Card Draw", "Removal",
    "Board Wipes", "Counters", "Tokens", "Utility",
]


def export_zone_name(zone: str) -> str:
    """Header label used in the text export ('Commanders' reads as 'Commander')."""
    return "Commander" if zone == "Commanders" else zone
