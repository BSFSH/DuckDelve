"""Tests for the match engine (matching.py)."""
from parsing import parse
from matching import match_all, COL_YOUR_LVL, COL_YOUR_ENCH

MAIN_HEADERS = ["Realm", "Area", "Mob", "Item", "Slot", "Type", "Spell", "Level"]
CRAFT_HEADERS = ["Realm", "Area", "Mob", "Item", "Type", "Sigil/Ingredient Use", "iLevel Req"]


def _main(item, slot, level, spell="", area="A1"):
    return {
        "Realm": "Chaos", "Area": area, "Mob": "m", "Item": item,
        "Slot": slot, "Type": "plate", "Spell": spell, "Level": str(level),
    }


def _craft(item, area="A1", ilevel="60"):
    return {
        "Realm": "Chaos", "Area": area, "Mob": "m", "Item": item,
        "Type": "ingredient", "Sigil/Ingredient Use": "crafting", "iLevel Req": ilevel,
    }


MAIN_ROWS = [
    _main("hauberk of the far traveler", "body", 45, "agility.ii", "Area1"),
    _main("hauberk of the far traveler", "body", 45, "agility.ii", "Area2"),  # 2nd drop loc
    _main("hauberk of the far traveler", "legs", 45, "wrongslot", "Area3"),   # wrong slot
    _main("mercenary's helmet of discipline", "head", 60, "wisdom.ii"),
    _main("vicious pike", "weapon", 55),
    _main("twisted nightmre harpoon", "weapon", 60),   # deliberate sheet typo
    _main("elven gorget", "jewel", 15),
]

CRAFT_ROWS = [
    _craft("pound of steel", "Grey Mountains", "45"),
    _craft("pound of steel", "Crystalline Mines", "60"),
    _craft("Kaidite flux", "Kaid Military Quarters", "60"),
]

MAIN = (MAIN_HEADERS, MAIN_ROWS)
CRAFT = (CRAFT_HEADERS, CRAFT_ROWS)


def _run(text):
    return match_all(parse(text), MAIN, CRAFT)


# ------------------------------------------------------------------------------
def test_exact_match_with_bracket_annotation():
    out = _run(" 1.) a glowing mithril mercenary's helmet of discipline [60|Head|wisdom2]")
    assert len(out.items) == 1
    row = out.items[0]
    assert row["Item"] == "mercenary's helmet of discipline"
    assert COL_YOUR_LVL in out.headers and COL_YOUR_ENCH in out.headers
    assert row[COL_YOUR_LVL] == "60"
    assert row[COL_YOUR_ENCH] == "wisdom2"


def test_no_bracket_means_no_annotation_columns():
    out = _run("On Head:  a glowing elven gorget")
    assert COL_YOUR_LVL not in out.headers
    assert len(out.items) == 1


def test_slot_disambiguation_excludes_wrong_slot():
    # Bracket says Body/45 -> the "legs" hauberk row must be dropped, both body rows kept.
    out = _run(" 4.) a bright hauberk of the far traveler [45|Body|agility2]")
    slots = {r["Slot"] for r in out.items}
    assert slots == {"body"}
    assert len(out.items) == 2  # two body drop locations


def test_fuzzy_fallback_hits_sheet_typo():
    # Sheet has "twisted nightmre harpoon"; user pastes the correct spelling.
    out = _run("11.) a shining twisted nightmare harpoon [60|Weap]")
    assert out.not_found == []
    assert len(out.items) == 1
    assert out.items[0]["Item"] == "twisted nightmre harpoon"


def test_craft_fallback_for_held_item():
    out = _run("17.) a pound of steel [1|Held Left]")
    assert out.items == []
    names = {r["Item"] for r in out.craft_items}
    assert names == {"pound of steel"}
    assert len(out.craft_items) == 2  # two farm locations, both kept


def test_craft_first_for_kaidite_flux():
    out = _run("13.) a Kaidite flux [1|Held Left]")
    assert len(out.craft_items) == 1
    assert out.craft_items[0]["Item"] == "Kaidite flux"


def test_not_found_keeps_bracket():
    out = _run(" 9.) a glowing spectral hammer from beyond [60|Weap]")
    assert out.items == []
    assert out.craft_items == []
    assert out.not_found == ["spectral hammer from beyond [60|Weap]"]
    detail = out.not_found_detailed[0]
    assert detail["name"] == "spectral hammer from beyond"
    assert detail["level"] == 60
    assert detail["bracket"] == "[60|Weap]"


def test_dedupe_repeated_paste():
    # Same item pasted twice should not duplicate the matched rows.
    out = _run("an elven gorget\nan elven gorget")
    assert len(out.items) == 1
