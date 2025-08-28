import pytest
from archive.armor_combos import (
    generate_armor_combinations,
    REQUIRED_SLOTS,
    take,
    get_unique_spells,
    filter_combinations_by_spells,
    refine_combinations_by_spell,   # NEW
)

# ---------------------------------------------------------------------------
# Existing fixtures / tests
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_items():
    return [
        {"Slot": "Body", "Item": "Iron Cuirass"},
        {"Slot": "Cloak", "Item": "Shadow Cloak"},
        {"Slot": "Feet", "Item": "Leather Boots"},
        {"Slot": "Hands", "Item": "Gloves of Grip"},
        {"Slot": "Head", "Item": "Helm of Light"},
        {"Slot": "Head", "Item": "Helm of Darkness"},
        {"Slot": "Legs", "Item": "Steel Greaves"},
        {"Slot": "Legs", "Item": "Iron Greaves"},
        {"Slot": "Jewel", "Item": "Ruby Ring"},
        {"Slot": "Jewel", "Item": "Emerald Ring"},
        {"Slot": "Jewel", "Item": "Sapphire Amulet"},
    ]

def test_generate_combos_contains_required_slots(sample_items):
    combos = list(generate_armor_combinations(sample_items))
    assert combos, "Should generate at least one combo"

    for combo in combos:
        for slot in REQUIRED_SLOTS:
            assert slot in combo["slots"]
            assert combo["slots"][slot] is not None

        assert "Jewel1" in combo["slots"]
        assert "Jewel2" in combo["slots"]
        assert combo["slots"]["Jewel1"] is not None
        assert combo["slots"]["Jewel2"] is not None

def test_generate_combos_and_print(sample_items):
    combos = take(5, generate_armor_combinations(sample_items))
    assert combos, "Should generate at least one combo"
    # touch the fields to ensure structure is correct
    for combo in combos:
        _ = [combo["slots"][s] for s in REQUIRED_SLOTS]

# ---------- tests for unique spells ------------------------------------
@pytest.fixture
def items_with_spells():
    return [
        {"Slot": "Body",  "Item": "X", "Spell": "Agility.II"},
        {"Slot": "Cloak", "Item": "Y", "Spell": " agility.ii "},   # same as above, different spacing/case
        {"Slot": "Head",  "Item": "Z", "Spell": "WISDOM.ii"},
        {"Slot": "Legs",  "Item": "W", "Spell": "dexterity.iii"},
        {"Slot": "Feet",  "Item": "F", "Spell": "bless.ii"},
        {"Slot": "Hands", "Item": "H", "Spell": "Direct.Enhance.II"},
        {"Slot": "Jewel", "Item": "J1", "Spell": ""},              # blank -> ignored
        {"Slot": "Jewel", "Item": "J2", "Spell": None},            # None -> ignored
        {"Slot": "Jewel", "Item": "J3", "Spell": "strength.ii"},
        {"Slot": "Jewel", "Item": "J4", "Spell": "water.resist"},
        {"Slot": "Jewel", "Item": "J5", "Spell": "bless.ii"},      # duplicate
    ]

def test_get_unique_spells_sorted_and_unique(items_with_spells):
    spells = get_unique_spells(items_with_spells)
    assert spells == [
        "agility.ii",
        "bless.ii",
        "dexterity.iii",
        "direct.enhance.ii",
        "strength.ii",
        "water.resist",
        "wisdom.ii",
    ]

# ---------- filtering combos by required spells -------------------
@pytest.fixture
def items_for_filtering():
    # Two possible Body items: one with agility.ii, one without.
    # Only two jewels (no agility) so the presence/absence of agility comes from Body.
    return [
        {"Slot": "Body",  "Item": "Agile Jerkin",   "Spell": "agility.ii"},
        {"Slot": "Body",  "Item": "Blessed Jerkin", "Spell": "bless.ii"},
        {"Slot": "Cloak", "Item": "Sage Cloak",     "Spell": "wisdom.ii"},
        {"Slot": "Feet",  "Item": "Leather Boots",  "Spell": "stability.i"},
        {"Slot": "Hands", "Item": "Gauntlets",      "Spell": "strength.ii"},
        {"Slot": "Head",  "Item": "Scout Helm",     "Spell": "dexterity.iii"},
        {"Slot": "Legs",  "Item": "Steel Greaves",  "Spell": "water.resist"},
        {"Slot": "Jewel", "Item": "Ruby Ring",      "Spell": "bless.ii"},
        {"Slot": "Jewel", "Item": "Emerald Ring",   "Spell": "strength.ii"},
    ]

def test_filter_combos_by_single_required_spell(items_for_filtering):
    all_combos = list(generate_armor_combinations(items_for_filtering))
    # We expect 2 combos total (2 Body choices * 1 of each other slot * 1 jewel pair).
    assert len(all_combos) == 2

    # Keep only combos that include agility.ii somewhere
    kept = filter_combinations_by_spells(all_combos, ["agility.ii"], mode="all")
    assert len(kept) == 1
    # sanity: confirm the kept one actually includes agility.ii
    contains_agility = any(
        (it and str(it.get("Spell", "")).strip().lower() == "agility.ii")
        for it in kept[0]["slots"].values()
    )
    assert contains_agility

# ---------- NEW: incremental refinement by an additional spell ---------------
def test_refine_combos_additional_spell(items_for_filtering):
    all_combos = list(generate_armor_combinations(items_for_filtering))

    # First user choice: agility.ii
    step1 = filter_combinations_by_spells(all_combos, "agility.ii", mode="all")
    assert step1, "First filter should keep at least one combo"

    # User adds another filter: dexterity.iii
    step2 = refine_combinations_by_spell(step1, "dexterity.iii")
    assert step2, "Second filter should still keep at least one combo"

    # Validate every remaining combo has BOTH spells
    for combo in step2:
        spells = {str(it.get("Spell", "")).strip().lower() for it in combo["slots"].values() if it}
        assert {"agility.ii", "dexterity.iii"}.issubset(spells)

    # Sanity check: one-shot "all" filter equals the two-step refine
    both_once = filter_combinations_by_spells(all_combos, ["agility.ii", "dexterity.iii"], mode="all")
    assert step2 == both_once
