"""
Match engine for DuckDelve.

Takes parsed paste items and resolves each one against the main gear sheet, then
the craft-mats sheet as a fallback. Matching runs in tiers:

    exact -> startswith -> contains -> fuzzy (difflib, fallback only)

When the new bracket metadata is present, the slot/level are used to pick the
correct variant among same-named rows (disambiguation) and to annotate the
results with the user's own level/enchants for display.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from parsing import ParsedItem, normalize_slot

# Similarity threshold for the fuzzy fallback tier.
FUZZY_THRESHOLD = 0.88
# Don't fuzzy-match very short names (too many false positives).
FUZZY_MIN_LEN = 5

# Annotation columns added to the main table when any item carried a bracket.
COL_YOUR_LVL = "Your Lvl"
COL_YOUR_ENCH = "Your Enchants"

# Slots that actually exist as gear on the main sheet (used to decide whether a
# bracket slot is meaningful for disambiguation / fuzzy restriction).
_GEAR_SLOTS = {"head", "hands", "body", "legs", "cloak", "feet", "jewel", "weapon", "shield"}

Row = Dict[str, Any]
Group = Tuple[str, List[Row]]  # (name_lower, rows sharing that name)


@dataclass
class MatchOutput:
    headers: List[str]
    items: List[Row]
    craft_headers: List[str]
    craft_items: List[Row]
    not_found: List[str]
    not_found_detailed: List[Dict[str, Any]] = field(default_factory=list)


# ------------------------------------------------------------------------------
# Index building
# ------------------------------------------------------------------------------
def detect_item_col(headers: List[str]) -> str:
    for h in headers:
        if h.strip().lower() in ("item", "name", "item name"):
            return h
    return headers[3] if len(headers) > 3 else (headers[0] if headers else "Item")


class SheetIndex:
    """Name index over a sheet's rows for fast tiered lookup."""

    def __init__(self, headers: List[str], rows: List[Row]):
        self.headers = headers
        self.rows = rows
        self.item_col = detect_item_col(headers)
        self.exact: Dict[str, List[Row]] = {}
        self.groups: List[Group] = []
        order: List[str] = []
        for r in rows:
            name = str(r.get(self.item_col, "")).strip().lower()
            if not name:
                continue
            if name not in self.exact:
                self.exact[name] = []
                order.append(name)
            self.exact[name].append(r)
        self.groups = [(n, self.exact[n]) for n in order]

    def row_slot(self, row: Row) -> Optional[str]:
        return normalize_slot(str(row.get("Slot", "")))


# ------------------------------------------------------------------------------
# Tier helpers
# ------------------------------------------------------------------------------
def _candidate_groups(index: SheetIndex, name: str, *, slot: Optional[str]) -> List[Group]:
    """Groups to consider for fuzzy matching, optionally restricted by slot."""
    if slot and slot in _GEAR_SLOTS:
        return [(n, rs) for (n, rs) in index.groups if any(index.row_slot(r) == slot for r in rs)]
    return index.groups


def _best_fuzzy(name: str, groups: List[Group]) -> List[Row]:
    if len(name) < FUZZY_MIN_LEN:
        return []
    best_score = 0.0
    best_rows: List[Row] = []
    matcher = SequenceMatcher()
    matcher.set_seq2(name)
    for cand_name, rows in groups:
        matcher.set_seq1(cand_name)
        # quick_ratio is a cheap upper bound; skip the real ratio if it can't win.
        if matcher.quick_ratio() < best_score:
            continue
        score = matcher.ratio()
        if score > best_score:
            best_score = score
            best_rows = rows
    return best_rows if best_score >= FUZZY_THRESHOLD else []


def _find_in_sheet(index: SheetIndex, item: ParsedItem) -> Tuple[List[Row], str]:
    """Return (candidate_rows, tier) for the first tier that yields a hit."""
    name = item.name.lower()

    # 1) exact
    if name in index.exact:
        return list(index.exact[name]), "exact"

    # 2) startswith
    sw = [r for (n, rs) in index.groups if n.startswith(name) for r in rs]
    if sw:
        return sw, "startswith"

    # 3) contains
    ct = [r for (n, rs) in index.groups if name in n for r in rs]
    if ct:
        return ct, "contains"

    # 4) fuzzy (fallback only; slot-restricted when we know the slot)
    fz = _best_fuzzy(name, _candidate_groups(index, name, slot=item.slot))
    if fz:
        return fz, "fuzzy"

    return [], "none"


def _disambiguate(index: SheetIndex, rows: List[Row], item: ParsedItem, tier: str) -> List[Row]:
    """Narrow candidate rows using bracket slot/level when available."""
    result = rows

    if item.slot and item.slot in _GEAR_SLOTS:
        slot_rows = [r for r in result if index.row_slot(r) == item.slot]
        if slot_rows:
            result = slot_rows
        elif tier == "fuzzy":
            # A fuzzy hit whose slot disagrees with the bracket is untrustworthy.
            return []

    if item.level is not None:
        lvl_rows = [r for r in result if _row_level(r) == item.level]
        if lvl_rows:
            result = lvl_rows

    return result


def _row_level(row: Row) -> Optional[int]:
    raw = str(row.get("Level", "")).strip()
    return int(raw) if raw.isdigit() else None


# ------------------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------------------
def match_all(
    parsed: List[ParsedItem],
    main_data: Tuple[List[str], List[Row]],
    craft_data: Tuple[List[str], List[Row]],
) -> MatchOutput:
    main_headers, main_rows = main_data
    craft_headers, craft_rows = craft_data

    main_index = SheetIndex(main_headers, main_rows)
    craft_index = SheetIndex(craft_headers, craft_rows)

    items: List[Row] = []
    craft_items: List[Row] = []
    not_found: List[str] = []
    not_found_detailed: List[Dict[str, Any]] = []
    any_bracket = False

    seen_main: set = set()
    seen_craft: set = set()

    def _sig(row: Row, headers: List[str]) -> Tuple:
        return tuple(str(row.get(h, "")) for h in headers)

    def _add_main(rows: List[Row], item: ParsedItem) -> None:
        nonlocal any_bracket
        has_bracket = item.bracket_raw is not None
        if has_bracket:
            any_bracket = True
        for r in rows:
            sig = _sig(r, main_headers)
            if sig in seen_main:
                continue
            seen_main.add(sig)
            annotated = dict(r)
            annotated[COL_YOUR_LVL] = str(item.level) if item.level is not None else ""
            annotated[COL_YOUR_ENCH] = ", ".join(item.enchants)
            items.append(annotated)

    def _add_craft(rows: List[Row]) -> None:
        for r in rows:
            sig = _sig(r, craft_headers)
            if sig in seen_craft:
                continue
            seen_craft.add(sig)
            craft_items.append(dict(r))

    for item in parsed:
        # "Held" bracket items are craft mats / consumables -> try craft first.
        craft_first = item.slot == "held"
        order = ("craft", "main") if craft_first else ("main", "craft")

        matched = False
        for which in order:
            if which == "main":
                rows, tier = _find_in_sheet(main_index, item)
                if rows:
                    rows = _disambiguate(main_index, rows, item, tier)
                if rows:
                    _add_main(rows, item)
                    matched = True
                    break
            else:  # craft
                rows, _ = _find_in_sheet(craft_index, item)
                if rows:
                    _add_craft(rows)
                    matched = True
                    break

        if not matched:
            label = item.name + (f" {item.bracket_display}" if item.bracket_display else "")
            not_found.append(label)
            not_found_detailed.append({
                "name": item.name,
                "level": item.level,
                "slot": (item.slot.title() if item.slot else ""),
                "enchants": ", ".join(item.enchants),
                "bracket": item.bracket_display or "",
            })

    headers = list(main_headers)
    if any_bracket:
        headers = headers + [COL_YOUR_LVL, COL_YOUR_ENCH]
        # Ensure every emitted row carries the annotation keys.
        for r in items:
            r.setdefault(COL_YOUR_LVL, "")
            r.setdefault(COL_YOUR_ENCH, "")

    return MatchOutput(
        headers=headers,
        items=items,
        craft_headers=list(craft_headers),
        craft_items=craft_items,
        not_found=not_found,
        not_found_detailed=not_found_detailed,
    )
