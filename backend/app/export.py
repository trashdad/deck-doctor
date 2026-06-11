"""Pure deck-export formatters.

Each formatter takes a list of resolved row dicts::

    {
        "name":      str,   # card name
        "zone":      str,   # deck zone (e.g. "Lands", "Ramp", "Commanders")
        "quantity":  int,
        "commander": bool,  # True when this card is the commander
    }

and returns a plain string ready for download or clipboard.

No I/O, no auth, no database — pure transformations so they are easy to test
and can be driven from both the saved-deck GET endpoint and the new stateless
POST endpoint.

CSV header sources
------------------
Moxfield  — header ``Count,Name,Edition,Condition,Language,Foil,Tag``
            Source: Moxfield import help / community gist
            (https://gist.github.com/Jerakin/24be913c6106546136c45d1d028f9af9)
            Moxfield matches columns by *name*, not position; these are the
            minimal columns it accepts (Count + Name required; rest optional
            and left blank here since we only know name + quantity).

Archidekt — header ``Quantity,Name,Finish,Condition,Edition Code,Collector Number,Category``
            Source: Archidekt spec guidance + community confirmation.
            Archidekt's flexible importer accepts custom column mappings; the
            columns here follow the canonical set documented in the spec
            (2026-06-11-export-formats-design.md).  Category is populated with
            the zone label (e.g. "Commander", "Lands") so Archidekt can put
            cards into the right category.
"""

from __future__ import annotations

import csv
import io
from typing import TypedDict

from .zones import ZONE_ORDER, export_zone_name


class ExportRow(TypedDict):
    name: str
    zone: str
    quantity: int
    commander: bool


# ---------------------------------------------------------------------------
# Text format  (same as the existing GET /decks/{id}/export)
# ---------------------------------------------------------------------------

def to_text(rows: list[ExportRow]) -> str:
    """Return the canonical Simmander text export format.

    Sections are ordered by ZONE_ORDER; within each zone cards are sorted
    alphabetically.  The commander line uses ``Commander: <name>`` (no qty).
    """
    by_zone: dict[str, list[tuple[str, int]]] = {}
    for row in rows:
        by_zone.setdefault(row["zone"], []).append((row["name"], row["quantity"]))

    lines: list[str] = []
    for zone in ZONE_ORDER:
        items = by_zone.get(zone)
        if not items:
            continue
        items.sort(key=lambda t: t[0])
        if zone == "Commanders":
            for name, _qty in items:
                lines.append(f"Commander: {name}")
            lines.append("")
            continue
        lines.append(f"// {export_zone_name(zone)}")
        for name, qty in items:
            lines.append(f"{qty} {name}")
        lines.append("")

    # Handle any zones not in ZONE_ORDER (e.g. "Unsorted")
    known = set(ZONE_ORDER)
    for zone, items in sorted(by_zone.items()):
        if zone in known:
            continue
        items.sort(key=lambda t: t[0])
        lines.append(f"// {zone}")
        for name, qty in items:
            lines.append(f"{qty} {name}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Moxfield CSV
# ---------------------------------------------------------------------------
# Header: Count,Name,Edition,Condition,Language,Foil,Tag
# Source: https://gist.github.com/Jerakin/24be913c6106546136c45d1d028f9af9
#         Moxfield matches by column *name*, not position.
# We emit only Count + Name; the other fields are left blank (accepted by
# Moxfield as unspecified / "any printing").
# ---------------------------------------------------------------------------

_MOXFIELD_HEADER = ["Count", "Name", "Edition", "Condition", "Language", "Foil", "Tag"]


def to_moxfield_csv(rows: list[ExportRow]) -> str:
    """Return a Moxfield-compatible CSV string."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_MOXFIELD_HEADER)
    for row in _sorted_rows(rows):
        writer.writerow([row["quantity"], row["name"], "", "", "", "", ""])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Archidekt CSV
# ---------------------------------------------------------------------------
# Header: Quantity,Name,Finish,Condition,Edition Code,Collector Number,Category
# Source: spec 2026-06-11-export-formats-design.md + Archidekt import docs.
# Category is populated with the zone label (commander → "Commander",
# others by zone name) so Archidekt files cards into the right section.
# ---------------------------------------------------------------------------

_ARCHIDEKT_HEADER = [
    "Quantity", "Name", "Finish", "Condition", "Edition Code", "Collector Number", "Category"
]


def _archidekt_category(row: ExportRow) -> str:
    """Map our zone name → Archidekt Category label."""
    if row["commander"]:
        return "Commander"
    return export_zone_name(row["zone"])


def to_archidekt_csv(rows: list[ExportRow]) -> str:
    """Return an Archidekt-compatible CSV string."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_ARCHIDEKT_HEADER)
    for row in _sorted_rows(rows):
        writer.writerow([
            row["quantity"],
            row["name"],
            "",                          # Finish (blank = Non-Foil)
            "",                          # Condition (blank = Near Mint)
            "",                          # Edition Code (any printing)
            "",                          # Collector Number
            _archidekt_category(row),
        ])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# ManaPool  (mass-entry paste format)
# ---------------------------------------------------------------------------
# One "qty name" line per card, commander included.
# ManaPool's mass-entry box accepts the simple "<qty> <name>" format,
# identical to what EDHREC and most deckbuilders produce.
# ---------------------------------------------------------------------------

def to_manapool(rows: list[ExportRow]) -> str:
    """Return a ManaPool mass-entry string (one ``<qty> <name>`` line per card)."""
    return "\n".join(
        f"{row['quantity']} {row['name']}"
        for row in _sorted_rows(rows)
    ) + "\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sorted_rows(rows: list[ExportRow]) -> list[ExportRow]:
    """Commander first, then remaining rows in ZONE_ORDER + alpha within zone."""
    zone_rank = {z: i for i, z in enumerate(ZONE_ORDER)}
    return sorted(
        rows,
        key=lambda r: (
            0 if r["commander"] else 1,
            zone_rank.get(r["zone"], len(ZONE_ORDER)),
            r["name"],
        ),
    )
