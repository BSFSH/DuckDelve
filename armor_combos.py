# armor_combos.py
from itertools import combinations, combinations_with_replacement, product, islice
import re
import sys

# ---- helpers to integrate with your existing get_items_from_sheet() output ----

def _rows_to_dicts(rows):
    """Convert CSV rows (with header row at index 0) into list[dict]."""
    headers = [h.strip() for h in rows[0]]
    return [
        {headers[i]: (row[i] if i < len(row) else "") for i in range(len(headers))}
        for row in rows[1:]
        if any((cell or "").strip() for cell in row)  # skip blank rows
    ]

# Slot normalization — adjust synonyms to match your sheet’s wording if needed.
_SLOT_SYNONYMS = {
    "body":  {"body", "chest", "torso", "armor", "robe", "breastplate", "hauberk", "cuirass", "jacket", "coat", "tunic", "vest"},
    "cloak": {"cloak", "cape", "mantle"},
    "feet":  {"feet", "boots", "shoes", "sabatons", "footwear", "greaves"},
    "hands": {"hands", "gloves", "gauntlets", "bracers"},
    "head":  {"head", "helm", "helmet", "hat", "hood", "circlet", "crown"},
    # Treat all rings/amulets/etc. as "jewel" for the two jewel slots:
    "jewel": {"jewel", "jewelry", "ring", "amulet", "neck", "necklace", "earring", "bracelet", "trinket"},
    # Explicitly ignore weapons:
    "weapon": {"weapon", "sword", "axe", "mace", "staff", "bow", "dagger", "spear", "polearm"}
}

def _canonical_slot(text):
    """Map a freeform slot/type string to a canonical slot name or None."""
    s = (text or "").strip().lower()
    if not s:
        return None
    # Exact or substring match against synonyms
    for canon, keys in _SLOT_SYNONYMS.items():
        if s in keys or any(k in s for k in keys):
            return canon
    return None

def _guess_slot(item):
    """
    Try to infer an item's slot from common header names ('Slot', 'Type', 'Category', etc.)
    Falls back to looking at the item name if needed.
    """
    # Prioritized header keys to inspect
    slot_like_keys = {"slot", "wear slot", "equipment slot", "slot type", "equip", "worn", "type", "category", "location"}
    for k, v in item.items():
        if k.strip().lower() in slot_like_keys:
            c = _canonical_slot(v)
            if c:
                return c
    # Fallback: infer from name/description tokens
    for name_key in ("Item", "item", "Name", "name", "Description", "desc"):
        if name_key in item:
            c = _canonical_slot(item[name_key])
            if c:
                return c
    return None

def _partition_by_slot(items_dicts):
    """Return dict of slot -> list[dict] for the armor slots we care about."""
    keep = { "body": [], "cloak": [], "feet": [], "hands": [], "head": [], "jewel": [] }
    for it in items_dicts:
        slot = _guess_slot(it)
        if slot in keep:            # only armor slots of interest
            keep[slot].append(it)
        # else: ignore non-armor or weapons
    return keep

def _item_label(it, preferred_keys=("Item","item","Name","name","Description","desc")):
    """Readable label for samples; tries common name keys first."""
    for k in preferred_keys:
        if k in it and it[k]:
            return str(it[k])
    # last resort: first non-empty stringy value
    for v in it.values():
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "<unnamed item>"

# ---- normalization + filtering to only use user-pasted items ----

def _norm_name(s: str) -> str:
    """Normalize a user/item name for matching."""
    s = (s or "").lower()

    # Remove 'You also see' and anything to the left of a colon
    s = re.sub(r'^you also see\s*', '', s)
    s = re.sub(r'^[^:]*:\s*', '', s)

    # Remove the phrase 'and a' when used as a joiner (e.g., "... and a ring")
    s = re.sub(r'(?:(?<=^)|(?<=[\s,]))and a\s+', ' ', s)

    # Remove leading articles
    s = re.sub(r'^(a|an|the)\s+', '', s)

    # Squash whitespace and strip punctuation except apostrophes
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r"[^\w\s']+", '', s)
    return s.strip()

def parse_user_items_text(text: str) -> list[str]:
    """Split pasted text into a de-duplicated list of normalized item names."""
    parts = re.split(r'[,\n]+', text)
    names, seen = [], set()
    for p in parts:
        n = _norm_name(p)
        if n and n not in seen:
            seen.add(n)
            names.append(n)
    return names

def filter_sheet_items_by_names(rows, wanted_names, name_keys=("Item","Name","item","name")):
    """Return (matched_items_as_dicts, missing_names) from the sheet rows."""
    dict_rows = _rows_to_dicts(rows)
    index = {}
    for d in dict_rows:
        for nk in name_keys:
            if nk in d and d[nk]:
                nm = _norm_name(d[nk])
                if nm and nm not in index:
                    index[nm] = d
                break
    matched, missing = [], []
    for n in wanted_names:
        it = index.get(n)
        if it:
            matched.append(it)
        else:
            missing.append(n)
    return matched, missing

# ---- main entry point for combinations ----

def generate_armor_combinations(all_items_dicts, *, jewel_pairing="distinct", sample=5, name_key=None):
    """
    Compute total armor loadouts and return a few sample combos for spot checks.

    Returns a dict:
      {
        "slot_counts": {...},
        "total_combinations": int,
        "samples": [ {body, cloak, feet, hands, head, jewels: [j1, j2]}, ... ]
      }
    """
    slots = _partition_by_slot(all_items_dicts)

    counts = {k: len(v) for k, v in slots.items()}
    nb, nc, nf, nh, hd, nj = (
        counts["body"], counts["cloak"], counts["feet"], counts["hands"], counts["head"], counts["jewel"]
    )

    # Jewel pairing math
    if nj == 0:
        pair_count = 0
        jewel_pairs_iter_factory = lambda: iter(())
    elif jewel_pairing == "distinct":
        pair_count = nj * (nj - 1) // 2
        jewel_pairs_iter_factory = lambda: combinations(slots["jewel"], 2)
    elif jewel_pairing == "with_replacement":
        pair_count = nj * (nj + 1) // 2
        jewel_pairs_iter_factory = lambda: combinations_with_replacement(slots["jewel"], 2)
    elif jewel_pairing == "ordered":
        pair_count = nj * nj
        jewel_pairs_iter_factory = lambda: product(slots["jewel"], repeat=2)
    else:
        raise ValueError("jewel_pairing must be one of: 'distinct', 'with_replacement', 'ordered'")

    # If any required slot is empty, total is 0.
    if min(nb, nc, nf, nh, hd, pair_count) == 0:
        return {
            "slot_counts": counts,
            "total_combinations": 0,
            "samples": []
        }

    total = nb * nc * nf * nh * hd * pair_count

    # Build a small sample without enumerating everything
    def combo_gen():
        for b in slots["body"]:
            for c in slots["cloak"]:
                for f in slots["feet"]:
                    for h in slots["hands"]:
                        for he in slots["head"]:
                            for j1, j2 in jewel_pairs_iter_factory():
                                yield (b, c, f, h, he, j1, j2)

    nk = name_key  # optional override
    def label(it):
        return it.get(nk) if (nk and nk in it and it[nk]) else _item_label(it)

    samples = []
    for (b, c, f, h, he, j1, j2) in islice(combo_gen(), sample):
        samples.append({
            "body":  label(b),
            "cloak": label(c),
            "feet":  label(f),
            "hands": label(h),
            "head":  label(he),
            "jewels": [label(j1), label(j2)]
        })

    return {
        "slot_counts": counts,
        "total_combinations": total,
        "samples": samples
    }

# ---- convenience: use the live sheet (all items) ----

def compute_armor_combo_summary(sample=5, jewel_pairing="distinct", name_key="Item"):
    """
    Pulls the sheet, converts rows to dicts, and returns a summary with counts + samples.
    Uses *all* items from the sheet.
    """
    from app import get_items_from_sheet  # imported here to avoid hard dependency at import time
    rows = get_items_from_sheet()
    items = _rows_to_dicts(rows)
    return generate_armor_combinations(items, jewel_pairing=jewel_pairing, sample=sample, name_key=name_key)

# ---- ONLY combine items the user pasted (matches against the live sheet) ----

def generate_combos_for_user_input(user_input_text: str, *, sample=5, jewel_pairing="distinct", name_key="Item"):
    """
    Filter the sheet to only the user-pasted items, then compute combos.
    Returns the usual summary, plus:
      - selected_item_count
      - not_found: list[str] of user-provided names not found in the sheet
    """
    from app import get_items_from_sheet  # imported here to avoid circular import on module load
    rows = get_items_from_sheet()
    wanted = parse_user_items_text(user_input_text)
    matched, missing = filter_sheet_items_by_names(rows, wanted)
    summary = generate_armor_combinations(matched, jewel_pairing=jewel_pairing, sample=sample, name_key=name_key)
    summary["selected_item_count"] = len(matched)
    summary["not_found"] = missing
    return summary

# ---- CLI (reads items from arg, file, or stdin; only uses selected items) ----

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Armor combo spot-check from pasted items only.")
    parser.add_argument("--items", help="Comma- or newline-separated items (quotes OK).", default="")
    parser.add_argument("--file", help="Path to a text file containing items.", default="")
    parser.add_argument("--stdin", help="Read items from STDIN.", action="store_true")
    parser.add_argument("--sample", type=int, default=3)
    parser.add_argument("--jewel_pairing", choices=["distinct","with_replacement","ordered"], default="distinct")
    parser.add_argument("--name_key", default="Item")
    args = parser.parse_args()

    if args.stdin:
        user_text = sys.stdin.read()
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            user_text = f.read()
    else:
        user_text = args.items

    if not (user_text or "").strip():
        print("No items provided. Use --items, --file, or --stdin.")
        sys.exit(1)

    summary = generate_combos_for_user_input(
        user_text,
        sample=args.sample,
        jewel_pairing=args.jewel_pairing,
        name_key=args.name_key
    )

    print("Selected items:", summary.get("selected_item_count", 0))
    if summary.get("not_found"):
        print("Not found in sheet:", summary["not_found"])
    print("Slot counts:", summary["slot_counts"])
    print("Total armor combinations:", summary["total_combinations"])
    for i, s in enumerate(summary["samples"], 1):
        print(f"{i}.", s)
