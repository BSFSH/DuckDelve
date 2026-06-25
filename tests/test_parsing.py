"""Tests for the paste parser (parsing.py)."""
from parsing import parse, normalize_slot


def _by_name(items):
    return {it.name: it for it in items}


# ------------------------------------------------------------------------------
# Section formats
# ------------------------------------------------------------------------------
def test_equipped_block():
    text = """ Items in use:
     On Head:  a glowing forlorn lyroe's cowl
    On Jewel:  an elven gorget
  Held Right:  a glowing steel vicious pike
"""
    items = parse(text)
    names = [it.name for it in items]
    assert names == ["forlorn lyroe's cowl", "elven gorget", "vicious pike"]
    # No bracket -> no metadata
    assert all(it.level is None and it.slot is None for it in items)


def test_guild_bank_enumeration_and_articles():
    text = """Items in Strongbox at The Bank of Chaos:
 1.) the silvered Overseer's Impaler
 7.) an honorbound footsteps
10.) a shining steel fine pike
"""
    names = [it.name for it in parse(text)]
    assert names == ["Overseer's Impaler", "honorbound footsteps", "fine pike"]


def test_inventory_quantity_and_flags():
    text = """Inventory:
  (w) A glowing forlorn lyroe's cowl
 (21) A woodsman's pie
 ( 4) A carafe of phoenix tears
      A ticket for The Surtur
  (h) A shining twisted nightmare harpoon
"""
    items = parse(text)
    by = _by_name(items)
    assert "forlorn lyroe's cowl" in by and by["forlorn lyroe's cowl"].qty is None
    assert by["woodsman's pie"].qty == 21
    assert by["carafe of phoenix tears"].qty == 4
    assert by["ticket for The Surtur"].qty is None
    assert "twisted nightmare harpoon" in by


# ------------------------------------------------------------------------------
# New personal-bank bracket format
# ------------------------------------------------------------------------------
def test_personal_bank_single_enchant():
    (it,) = parse(" 1.) a glowing mithril mercenary's helmet of discipline [60|Head|wisdom2]")
    assert it.name == "mercenary's helmet of discipline"
    assert it.level == 60
    assert it.slot == "head"
    assert it.enchants == ["wisdom2"]
    assert it.bracket_display == "[60|Head|wisdom2]"


def test_personal_bank_two_enchants():
    (it,) = parse("15.) a bright cloak of blood red leaves [30|Cloak|MP1|agility1]")
    assert it.name == "cloak of blood red leaves"
    assert it.level == 30
    assert it.slot == "cloak"
    assert it.enchants == ["MP1", "agility1"]


def test_personal_bank_weapon_and_held():
    weap, held = parse(
        " 8.) a glowing greatsword of conquest [60|Weap|S5]\n"
        "17.) a pound of steel [1|Held Left]"
    )
    assert weap.name == "greatsword of conquest"
    assert weap.slot == "weapon"
    assert weap.enchants == ["S5"]
    assert held.name == "pound of steel"
    assert held.slot == "held"
    assert held.level == 1


# ------------------------------------------------------------------------------
# Comma handling
# ------------------------------------------------------------------------------
def test_comma_in_name_preserved():
    (it,) = parse("a voluminous, cowled brown robe")
    assert it.name == "voluminous, cowled brown robe"


def test_scoped_comma_split_ground_list():
    names = [it.name for it in parse("you also see a sword, a shield, and a helm")]
    assert names == ["sword", "shield", "helm"]


# ------------------------------------------------------------------------------
# Slot normalization
# ------------------------------------------------------------------------------
def test_normalize_slot():
    assert normalize_slot("Weap") == "weapon"
    assert normalize_slot("Held Left") == "held"
    assert normalize_slot("Held Right") == "held"
    assert normalize_slot("Jewel") == "jewel"
    assert normalize_slot("Head") == "head"
    assert normalize_slot("") is None


# ------------------------------------------------------------------------------
# Misc robustness
# ------------------------------------------------------------------------------
def test_section_headers_skipped():
    items = parse("Items in use:\nInventory:\nItems in Strongbox at Bank of Olmran:")
    assert items == []


def test_empty_input():
    assert parse("") == []
    assert parse("\n\n   \n") == []
