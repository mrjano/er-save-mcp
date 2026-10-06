"""Replays the four hand-made edits of 2026-10-06 and requires byte-identical output.

The saves are personal and never committed: point ERSAVE_FIXTURES at the folder
holding the 2026-10-06-* backups (default ~/.local/share/ps5-jb/saves).
"""

import os
from pathlib import Path

import pytest

from ersave.edit import apply_operations
from ersave.save import load

ROOT = Path(os.environ.get("ERSAVE_FIXTURES", Path.home() / ".local/share/ps5-jb/saves"))
PRE = "1258a7c3/CUSA18581/memory.dat"
RONCHAS = 1

EDIT1 = [
    {"op": "runes_for_level", "target_level": 140},
    {"op": "add_item", "item": "Blasphemous Blade", "upgrade": 10},
    {"op": "add_item", "item": "Erdtree Seal", "upgrade": 10},
    {"op": "add_item", "item": "Greatsword", "upgrade": 25, "affinity": "heavy", "ash_of_war": "Lion's Claw",
     "category": "melee_armaments"},
    *({"op": "add_item", "item": n} for n in [
        "Fire Prelate Helm", "Fire Prelate Armor", "Fire Prelate Gauntlets", "Fire Prelate Greaves",
        "Bull-Goat Helm", "Bull-Goat Armor", "Bull-Goat Gauntlets", "Bull-Goat Greaves",
        "Shard of Alexander", "Godfrey Icon", "Fire Scorpion Charm", "Erdtree's Favor +2",
        "Starscourge Heirloom", "Claw Talisman", "Axe Talisman", "Great-Jar's Arsenal"]),
    {"op": "add_item", "item": "Flame, Grant Me Strength"},
    {"op": "add_item", "item": "Golden Vow", "category": "incantations"},
    {"op": "add_item", "item": "Mimic Tear Ashes", "upgrade": 10},
    {"op": "add_item", "item": "Spirit Calling Bell"},
]
EDIT2 = [
    {"op": "set_talisman_slots", "total": 4},
    {"op": "add_item", "item": "Golden Seed", "quantity": 30},
    {"op": "add_item", "item": "Sacred Tear", "quantity": 12},
    {"op": "add_item", "item": "Talisman Pouch", "quantity": 3},
]
EDIT3 = [
    *({"op": "unlock_grace", "grace": g} for g in [
        "Chamber Outside the Plaza", "Palace Approach Ledge-Road",
        "Dynasty Mausoleum Entrance", "Dynasty Mausoleum Midpoint"]),
    *({"op": "unlock_map", "region": f} for f in [
        62010, 62011, 62012, 62020, 62021, 62022, 62030, 62031, 62032, 62040, 62041,
        62050, 62051, 62052, 62060, 62061, 62062, 62063, 62064]),
]
EDIT4 = [
    {"op": "unlock_grace", "grace": "Altus Plateau (Altus Plateau)"},
    {"op": "add_item", "item": "Giant-Crusher", "upgrade": 25, "affinity": "heavy", "ash_of_war": "Barbaric Roar"},
    {"op": "add_item", "item": "Prelate's Inferno Crozier", "upgrade": 25},
    {"op": "add_item", "item": "Rotten Greataxe", "upgrade": 25},
    {"op": "add_item", "item": "Troll's Hammer", "upgrade": 25},
]
CASES = [
    ("2026-10-06-pre-edit/" + PRE, "2026-10-06-edited/memory.dat", EDIT1),
    ("2026-10-06-pre-edit2/" + PRE, "2026-10-06-edited2/memory.dat", EDIT2),
    ("2026-10-06-pre-edit3/" + PRE, "2026-10-06-edited3/memory.dat", EDIT3),
    ("2026-10-06-pre-edit4/" + PRE, "2026-10-06-edited4/memory.dat", EDIT4),
]


@pytest.mark.parametrize("before,after,ops", CASES, ids=["edit1", "edit2", "edit3", "edit4"])
def test_reproduces_hand_edit(before, after, ops):
    src, want = ROOT / before, ROOT / after
    if not src.exists() or not want.exists():
        pytest.skip("fixtures not available")
    data = load(src.read_bytes())
    ed = apply_operations(data, RONCHAS, ops)
    ed.validate()
    got, exp = bytes(ed.data), want.read_bytes()
    diff = [hex(i) for i, (a, b) in enumerate(zip(got, exp)) if a != b]
    assert not diff, f"{len(diff)} bytes differ, first at {diff[:5]}"
