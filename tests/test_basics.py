import os
from pathlib import Path

import pytest

from ersave import db
from ersave.edit import EditError, apply_operations, rune_cost, runes_between
from ersave.save import characters, load

ROOT = Path(os.environ.get("ERSAVE_FIXTURES", Path.home() / ".local/share/ps5-jb/saves"))
SAVE = ROOT / "2026-10-06-pre-edit/1258a7c3/CUSA18581/memory.dat"


def test_rune_costs():
    assert rune_cost(1) == 673
    assert runes_between(1, 140) == 5_702_929


def test_item_lookup():
    assert db.resolve_item("Blasphemous Blade")["id"] == 3140000
    with pytest.raises(LookupError, match="Candidates"):
        db.resolve_item("Golden Vow")
    assert db.kind(db.resolve_item("Spirit Calling Bell")) == "key"
    assert db.kind(db.resolve_item("Memory of Grace")) == "goods"
    assert db.resolve_grace("Chamber Outside the Plaza")["flag"] == 0x12A84


@pytest.mark.skipif(not SAVE.exists(), reason="fixtures not available")
def test_characters_and_refusals():
    data = load(SAVE.read_bytes())
    names = [(c.index, c.name, c.level) for c in characters(data)]
    assert (1, "Ronchas", 1) in names
    with pytest.raises(EditError, match="somber"):
        apply_operations(data, 1, [{"op": "add_item", "item": "Blasphemous Blade", "affinity": "heavy",
                                    "ash_of_war": "Lion's Claw"}])
    with pytest.raises(EditError, match="boss arena"):
        apply_operations(load(SAVE.read_bytes()), 1, [{"op": "unlock_grace", "grace": "Redmane Castle Plaza"}])
    with pytest.raises(EditError, match="upgrades to"):
        apply_operations(load(SAVE.read_bytes()), 1, [{"op": "add_item", "item": "Blasphemous Blade", "upgrade": 25}])
