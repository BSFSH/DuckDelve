# armor_combos.py
from __future__ import annotations
from itertools import product, combinations, combinations_with_replacement, islice
from typing import Dict, Iterable, Iterator, List, Tuple, Any, Set

# Exactly the six armor slots you use
REQUIRED_SLOTS: Tuple[str, ...] = ("Body", "Cloak", "Feet", "Hands", "Head", "Legs")
JEWEL_SLOTS = {"jewel", "jewels"}  # case-insensitive check against Slot column

# -------------------------- small utils --------------------------------------

def _norm(s: Any) -> str:
    return str(s or "").strip()

def _slot(s: Any) -> str:
    """Title-case slot name (e.g., 'head' -> 'Head')."""
    return _norm(s).title()

def _canonical_slot(s: Any) -> str:
    """
    Canonicalize slot for internal comparisons/deduping.
    'jewel' / 'jewels' => 'Jewel', otherwise TitleCase (Body, Cloak, ...).
    """
    raw = _norm(s)
    if raw.lower() in JEWEL_SLOTS:
        return "Jewel"
    return _slot(raw)

def _is_weapon_or_shield(item: Dict[str, Any]) -> bool:
    t = _norm(item.get("Type")).lower()
    sl = _norm(item.get("Slot")).lower()
    return t in {"weapon", "weapons", "shield", "shields"} or sl in {"weapon", "weapons", "shield", "shields"}

# -------------------------- deduplication ------------------------------------

def dedupe_items(
    items: List[Dict[str, Any]],
    key_fields: Tuple[str, ...] = ("Slot", "Item", "Spell"),
) -> List[Dict[str, Any]]:
    """
    Remove duplicate item rows by a content key (default: Slot, Item, Spell).
    Normalizes:
      - Slot via _canonical_slot (handles 'jewel' vs 'jewels', title-casing)
      - All fields: trimmed, lower-cased strings
    """
    seen: Set[Tuple[str, ...]] = set()
    out: List[Dict[str, Any]] = []

    for it in items:
        k: List[str] = []
        for f in key_fields:
            v = it.get(f)
            if f.lower() == "slot":
                k.append(_canonical_slot(v).lower())
            else:
                k.append(_norm(v).lower())
        tup = tuple(k)
        if tup in seen:
            continue
        seen.add(tup)
        out.append(it)
    return out

# ------------------------- partitioning --------------------------------------

def partition_session_items(items: List[Dict[str, Any]]) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    """
    Split items into:
      - slot_pools: dict of required slot -> list of candidate items
      - jewels: list of jewel items
    Weapons/shields are excluded.
    **Now dedupes globally before partitioning** so identical rows don't inflate combos.
    """
    # Global dedupe first
    items = dedupe_items(items)

    slot_pools: Dict[str, List[Dict[str, Any]]] = {s: [] for s in REQUIRED_SLOTS}
    jewels: List[Dict[str, Any]] = []

    for it in items:
        if _is_weapon_or_shield(it):
            continue
        slot_val = _canonical_slot(it.get("Slot"))
        if slot_val == "Jewel":
            jewels.append(it)
        elif slot_val in slot_pools:
            slot_pools[slot_val].append(it)

    return slot_pools, jewels

# ------------------------ jewel picking --------------------------------------

def _jewel_picker(
    jewels: List[Dict[str, Any]],
    need: int = 2,
    allow_same_item_twice: bool = False,
) -> Iterable[Tuple[Dict[str, Any], ...]]:
    if need <= 0:
        yield tuple()
        return
    if allow_same_item_twice:
        yield from combinations_with_replacement(jewels, need)
    else:
        yield from combinations(jewels, need)

# --------------------- combination generation --------------------------------

def generate_armor_combinations(
    items: List[Dict[str, Any]],
    jewels_needed: int = 2,
    allow_same_jewel_twice: bool = False,
) -> Iterator[Dict[str, Any]]:
    """
    Yield combos that contain one item for each of:
      Body, Cloak, Feet, Hands, Head, Legs
    plus exactly `jewels_needed` jewels.

    Each yielded record:
      { "slots": { "Body": {...}, "Cloak": {...}, ..., "Jewel1": {...}, "Jewel2": {...} } }

    NOTE: duplicates in the input (by Slot+Item+Spell) are deduplicated up-front.
    """
    slot_pools, jewel_pool = partition_session_items(items)

    # All 6 armor slots must have at least one candidate
    if any(not slot_pools.get(s) for s in REQUIRED_SLOTS):
        return iter(())  # empty iterator

    if len(jewel_pool) < jewels_needed and not allow_same_jewel_twice:
        return iter(())

    per_slot_lists = [slot_pools[s] for s in REQUIRED_SLOTS]

    for body, cloak, feet, hands, head, legs in product(*per_slot_lists):
        if jewels_needed == 2:
            jewel_pairs = (
                combinations_with_replacement(jewel_pool, 2)
                if allow_same_jewel_twice else
                combinations(jewel_pool, 2)
            )
        elif jewels_needed <= 0:
            jewel_pairs = [tuple()]
        else:
            jewel_pairs = (
                combinations_with_replacement(jewel_pool, jewels_needed)
                if allow_same_jewel_twice else
                combinations(jewel_pool, jewels_needed)
            )

        for jp in jewel_pairs:
            slot_map = {
                "Body": body, "Cloak": cloak, "Feet": feet,
                "Hands": hands, "Head": head, "Legs": legs,
            }
            for i, j in enumerate(jp, start=1):
                slot_map[f"Jewel{i}"] = j
            # If jewels_needed > len(jp), pad (keeps keys stable)
            for k in range(len(jp) + 1, jewels_needed + 1):
                slot_map[f"Jewel{k}"] = None

            yield {"slots": slot_map}

# -------------------------- convenience --------------------------------------

def take(n: int, it: Iterable[Any]) -> List[Any]:
    """Return the first n items from an iterator/generator."""
    return list(islice(it, n))

# ------------------------ unique spells helper --------------------------------

def get_unique_spells(
    items: List[Dict[str, Any]],
    *,
    field: str = "Spell",
    lowercase: bool = True,
    drop_blanks: bool = True,
) -> List[str]:
    """
    Return the list of unique spells available across items, alphabetized.
    """
    seen = set()
    result: List[str] = []

    for it in items:
        raw = it.get(field)
        if raw is None:
            if drop_blanks:
                continue
            normalized = ""
        else:
            normalized = str(raw).strip()
        if lowercase:
            normalized = normalized.lower()

        if drop_blanks and not normalized:
            continue

        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    result.sort(key=lambda s: s.lower())
    return result

# ----------------------- filtering by spells ----------------------------------

def _combo_spells(
    combo: Dict[str, Any],
    *,
    field: str = "Spell",
    lowercase: bool = True,
    drop_blanks: bool = True,
) -> Set[str]:
    """
    Collect the set of spells present across all items in a combo.
    """
    out: Set[str] = set()
    slots = combo.get("slots", {}) or {}
    for it in slots.values():
        if not it:
            continue
        raw = it.get(field)
        if raw is None and drop_blanks:
            continue
        val = "" if raw is None else str(raw).strip()
        if lowercase:
            val = val.lower()
        if drop_blanks and not val:
            continue
        out.add(val)
    return out

def filter_combinations_by_spells(
    combos: Iterable[Dict[str, Any]],
    required_spells: Iterable[str] | str,
    *,
    mode: str = "all",          # "all" = every spell required; "any" = at least one
    field: str = "Spell",
    lowercase: bool = True,
) -> List[Dict[str, Any]]:
    """
    Keep only those combos that include the required spell(s).

    Args:
        combos: iterable of combo dicts from `generate_armor_combinations`
        required_spells: a string or list of strings (e.g., "agility.ii" or ["agility.ii", "bless.ii"])
        mode: "all" (default) requires every spell to be present somewhere in the combo;
              "any" keeps combos that contain at least one of the required spells.
        field: key that holds the spell on each item (default "Spell")
        lowercase: normalize comparison case-insensitively
    """
    if isinstance(required_spells, str):
        req = [required_spells]
    else:
        req = list(required_spells)

    req_norm: Set[str] = set()
    for s in req:
        v = "" if s is None else str(s).strip()
        if lowercase:
            v = v.lower()
        if v:
            req_norm.add(v)

    if not req_norm:
        # No criteria -> return everything as a list
        return list(combos)

    keep: List[Dict[str, Any]] = []
    for combo in combos:
        spells = _combo_spells(combo, field=field, lowercase=lowercase, drop_blanks=True)
        if mode == "any":
            if spells & req_norm:
                keep.append(combo)
        else:  # "all"
            if req_norm.issubset(spells):
                keep.append(combo)
    return keep

def refine_combinations_by_spell(
    combos: Iterable[Dict[str, Any]],
    new_required_spell: str,
    *,
    field: str = "Spell",
    lowercase: bool = True,
) -> List[Dict[str, Any]]:
    """
    Incrementally filter an already-filtered list by ONE additional spell.
    Equivalent to: filter_combinations_by_spells(combos, [new_required_spell], mode="all").
    """
    return filter_combinations_by_spells(
        combos,
        [new_required_spell],
        mode="all",
        field=field,
        lowercase=lowercase,
    )
