"""Human-readable "what changed" summary between the live and candidate cards.json."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

_LIST_MAX = 25


@dataclass
class ContentDiff:
    new_cards: list[tuple[str, str]] = field(default_factory=list)      # (name, set)
    removed: list[str] = field(default_factory=list)
    renamed: list[tuple[str, str]] = field(default_factory=list)        # (old, new)
    changed: int = 0                                                     # same id, data changed
    new_set_codes: list[str] = field(default_factory=list)              # sets never seen before
    new_cards_by_set: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"new_cards": len(self.new_cards), "removed": len(self.removed),
                "renamed": len(self.renamed), "changed": self.changed,
                "new_set_codes": self.new_set_codes, "new_cards_by_set": self.new_cards_by_set,
                "new_card_names": [n for n, _ in self.new_cards[:_LIST_MAX]],
                "removed_names": self.removed[:_LIST_MAX], "renamed_pairs": self.renamed[:_LIST_MAX]}


def content_diff(current: list[dict], candidate: list[dict]) -> ContentDiff:
    cur_by_oracle = {c["oracle_id"]: c for c in current}
    cand_by_oracle = {c["oracle_id"]: c for c in candidate}
    cur_by_id = {c["id"]: c for c in current}
    known_sets = {c.get("set", "") for c in current}

    d = ContentDiff()
    new = [c for oid, c in cand_by_oracle.items() if oid not in cur_by_oracle]
    d.new_cards = sorted((c["name"], c.get("set", "")) for c in new)
    d.removed = sorted(c["name"] for oid, c in cur_by_oracle.items() if oid not in cand_by_oracle)
    d.renamed = sorted((cur_by_oracle[oid]["name"], c["name"]) for oid, c in cand_by_oracle.items()
                       if oid in cur_by_oracle and cur_by_oracle[oid]["name"] != c["name"])
    d.changed = sum(1 for c in candidate if c["id"] in cur_by_id and cur_by_id[c["id"]] != c)
    by_set = Counter(c.get("set", "") for c in new)
    d.new_cards_by_set = dict(by_set.most_common())
    d.new_set_codes = sorted(s for s in by_set if s not in known_sets)
    return d


def render(d: ContentDiff) -> list[str]:
    lines = [f"new cards: {len(d.new_cards):,}   removed: {len(d.removed):,}   "
             f"renamed: {len(d.renamed):,}   changed (same id): {d.changed:,}"]
    if d.new_set_codes:
        lines.append("new set codes: " + ", ".join(d.new_set_codes))
    if d.new_cards_by_set:
        lines.append("new cards by set: " + ", ".join(f"{s or '?'}={n}" for s, n in
                                                    list(d.new_cards_by_set.items())[:20]))
    if d.new_cards:
        shown = ", ".join(n for n, _ in d.new_cards[:_LIST_MAX])
        more = f" … (+{len(d.new_cards) - _LIST_MAX})" if len(d.new_cards) > _LIST_MAX else ""
        lines.append(f"e.g. new: {shown}{more}")
    if d.removed:
        lines.append("removed: " + ", ".join(d.removed[:_LIST_MAX]))
    if d.renamed:
        lines.append("renamed: " + ", ".join(f"{a} -> {b}" for a, b in d.renamed[:_LIST_MAX]))
    return lines
