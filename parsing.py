"""
Paste parser for DuckDelve.

Turns a block of game output (equipped list, guild bank, personal bank, or
inventory) into a list of ``ParsedItem`` records. Pure functions only -- no I/O,
no sheet access -- so it can be unit-tested in isolation.

The new personal-bank format appends a metadata tag to each line:

    a glowing mithril mercenary's helmet of discipline [60|Head|wisdom2]
    a bright cloak of blood red leaves [30|Cloak|MP1|agility1]
    a pound of steel [1|Held Left]

i.e. ``[ level | slot | enchant(s) ]`` with one or two enchant codes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ------------------------------------------------------------------------------
# Vocabulary (order matters only within a list; longest-ish first is fine)
# ------------------------------------------------------------------------------
ENCHANT_PREFIXES: Tuple[str, ...] = (
    "brilliant",
    "lustrous",
    "glowing",
    "shining",
    "bright",
    "silvered",
)
MATERIAL_PREFIXES: Tuple[str, ...] = (
    "bronze", "iron", "steel", "alloy", "mithril", "laen",
    "wool", "cotton", "silk", "gossamer", "wispweave", "ebonweave",
    "leather", "rough", "embossed", "suede", "wyvern scale", "enchanted",
    "maple", "oak", "yew", "rosewood", "ironwood", "ebony",
)

# bracket/equipped slot label -> sheet ``Slot`` value
SLOT_MAP = {
    "head": "head",
    "hands": "hands",
    "body": "body",
    "legs": "legs",
    "cloak": "cloak",
    "feet": "feet",
    "jewel": "jewel",
    "jewels": "jewel",
    "weap": "weapon",
    "weapon": "weapon",
    "weapons": "weapon",
    "shield": "shield",
    "shields": "shield",
    "held": "held",
    "held left": "held",
    "held right": "held",
}

# ------------------------------------------------------------------------------
# Regexes
# ------------------------------------------------------------------------------
# Trailing "[ ... ]" metadata tag.
_BRACKET_RE = re.compile(r"\[([^\]]*)\]\s*$")
# Equipped slot label, e.g. "On Head:", "Held Right:", "Wielded:".
_EQUIP_LABEL_RE = re.compile(r"^\s*(?:on|held|wielded|worn)\b[^:]*:\s*", re.IGNORECASE)
# Leading enumeration / bullet, e.g. " 1.) ", "10.) ", "12.", "- ".
_ENUM_RE = re.compile(r"^\s*(?:\d+\s*[.)]+\s*|[-+*•]\s+)")
# Leading "(w) (h) (21) ( 4)" quantity / flag marker.
_QTY_RE = re.compile(r"^\s*\(\s*([^)]*?)\s*\)\s*")
# Leading article.
_ARTICLE_RE = re.compile(r"^\s*(?:a|an|the)\s+", re.IGNORECASE)
# "you also see" room phrase.
_YOU_ALSO_SEE_RE = re.compile(r"you also see", re.IGNORECASE)
# Scoped ground-list comma split: only at boundaries that precede an article so
# comma-in-name items (e.g. "voluminous, cowled brown robe") survive intact.
_GROUND_SPLIT_RE = re.compile(
    r"\s*,\s+and\s+(?=(?:a|an|the)\s)"   # ", and a ..."
    r"|\s*,\s+(?=(?:a|an|the)\s)"        # ", a ..."
    r"|\s+and\s+(?=(?:a|an|the)\s)",     # " and a ..."
    re.IGNORECASE,
)

_SUFFIX_TO_REMOVE = " is here."


@dataclass
class ParsedItem:
    raw: str                                    # original source line
    name: str                                   # cleaned base name for matching
    level: Optional[int] = None                 # from bracket
    slot: Optional[str] = None                  # from bracket, normalized
    enchants: List[str] = field(default_factory=list)  # bracket enchant codes, verbatim
    qty: Optional[int] = None                   # inventory "(21)" / "( 4)"
    bracket_raw: Optional[str] = None           # inner bracket text, for display

    @property
    def bracket_display(self) -> Optional[str]:
        """The bracket as it should appear to a user, e.g. '[60|Head|wisdom2]'."""
        return f"[{self.bracket_raw}]" if self.bracket_raw else None


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def _normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def normalize_slot(slot: Optional[str]) -> Optional[str]:
    """Map a bracket/equipped slot label to the sheet's Slot vocabulary."""
    if not slot:
        return None
    key = _normalize_spaces(slot).lower()
    return SLOT_MAP.get(key, key)


def _strip_prefix_loop(s: str, prefixes: Tuple[str, ...]) -> str:
    """Repeatedly strip any leading whole-word prefix from ``prefixes``."""
    changed = True
    while changed:
        changed = False
        lowered = s.lower()
        for p in prefixes:
            if lowered.startswith(p + " "):
                s = s[len(p) + 1:]
                changed = True
                break
    return s


def _extract_bracket(text: str) -> Tuple[str, Optional[int], Optional[str], List[str], Optional[str]]:
    """
    Pull a trailing ``[level|slot|enchant...]`` tag off ``text``.

    Returns (text_without_bracket, level, normalized_slot, enchants, bracket_raw).
    """
    m = _BRACKET_RE.search(text)
    if not m:
        return text, None, None, [], None

    inner = m.group(1).strip()
    text = text[: m.start()].rstrip()

    fields = [f.strip() for f in inner.split("|")]
    level: Optional[int] = None
    slot: Optional[str] = None
    enchants: List[str] = []

    if fields:
        if fields[0].isdigit():
            level = int(fields[0])
    if len(fields) > 1:
        slot = normalize_slot(fields[1])
    if len(fields) > 2:
        enchants = [f for f in fields[2:] if f]

    return text, level, slot, enchants, inner


def _strip_leading_markers(text: str) -> Tuple[str, Optional[int]]:
    """Strip a leading enumeration and/or a ``(w)/(h)/(21)`` marker; capture qty."""
    text = _ENUM_RE.sub("", text, count=1)
    qty: Optional[int] = None
    m = _QTY_RE.match(text)
    if m:
        inner = m.group(1).strip()
        if inner.isdigit():
            qty = int(inner)
        text = text[m.end():]
    return text, qty


def _clean_name(text: str) -> str:
    """Strip article, enchant, and material prefixes; tidy whitespace."""
    text = _ARTICLE_RE.sub("", text).strip()
    text = _strip_prefix_loop(text, ENCHANT_PREFIXES)
    text = _strip_prefix_loop(text, MATERIAL_PREFIXES)
    if text.lower().endswith(_SUFFIX_TO_REMOVE):
        text = text[: -len(_SUFFIX_TO_REMOVE)]
    # Defensive: drop stray leading/trailing commas left by a ground-list split.
    text = text.strip().strip(",").strip()
    return _normalize_spaces(text)


def _is_section_header(line: str) -> bool:
    """Lines like 'Inventory:' / 'Items in Strongbox at ...:' carry no item."""
    return line.rstrip().endswith(":")


def _segment_to_item(segment: str) -> Optional[ParsedItem]:
    raw = segment
    text, level, slot, enchants, bracket_raw = _extract_bracket(segment)
    text, qty = _strip_leading_markers(text)
    name = _clean_name(text)
    if not name:
        return None
    return ParsedItem(
        raw=raw.strip(),
        name=name,
        level=level,
        slot=slot,
        enchants=enchants,
        qty=qty,
        bracket_raw=bracket_raw,
    )


# ------------------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------------------
def parse(raw_text: str) -> List[ParsedItem]:
    """Parse a pasted block of game output into ``ParsedItem`` records."""
    if not raw_text:
        return []

    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    items: List[ParsedItem] = []

    for line in text.split("\n"):
        line = line.strip()
        if not line or _is_section_header(line):
            continue

        line = _YOU_ALSO_SEE_RE.sub(" ", line).strip()
        line = _EQUIP_LABEL_RE.sub("", line)
        if not line:
            continue

        # Only comma-split when there's no metadata bracket (i.e. a ground list).
        if _BRACKET_RE.search(line):
            segments = [line]
        else:
            segments = _GROUND_SPLIT_RE.split(line)

        for seg in segments:
            if not seg or not seg.strip():
                continue
            item = _segment_to_item(seg)
            if item is not None:
                items.append(item)

    return items
