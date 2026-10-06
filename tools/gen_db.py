"""Generate ersave/data/*.json from a checkout of oisis/EldenRing-SaveForge (GPL-3.0).

    uv run python tools/gen_db.py /path/to/EldenRing-SaveForge
"""

import json
import re
import shutil
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "ersave" / "data"

ITEM_RE = re.compile(
    r'0x([0-9A-Fa-f]{8}): \{Name: "((?:[^"\\]|\\.)*)", Category: "([a-z_]+)", '
    r"(?:SubCategory: \w+, )?MaxInventory: (\d+), MaxStorage: (\d+), MaxUpgrade: (\d+)[^}]*?"
    r'(?:Flags: \[\]string\{([^}]*)\})?\}'
)
ITEM_FILES = [
    "melee_armaments", "ranged_and_catalysts", "shields", "arrows_and_bolts",
    "head", "chest", "arms", "legs", "talismans", "ashes_of_war", "ashes",
    "incantations", "sorceries", "tools", "key_items", "bolstering_materials",
    "crafting_materials", "info",
]


def items(data: Path) -> list[dict]:
    out = {}
    for name in ITEM_FILES:
        for m in ITEM_RE.finditer((data / f"{name}.go").read_text()):
            item_id = int(m.group(1), 16)
            flags = re.findall(r'"([a-z_]+)"', m.group(7) or "")
            out[item_id] = {
                "id": item_id,
                "name": m.group(2).replace('\\"', '"'),
                "category": m.group(3),
                "max_inventory": int(m.group(4)),
                "max_storage": int(m.group(5)),
                "max_upgrade": int(m.group(6)),
                "flags": flags,
            }
    return sorted(out.values(), key=lambda i: i["id"])


def graces(data: Path) -> list[dict]:
    src = (data / "graces.go").read_text()
    out = []
    for m in re.finditer(r'0x([0-9A-Fa-f]+): (G|B|Cat|HG)\("([^"]+)"(?:, (\d+))?\)', src):
        out.append({
            "flag": int(m.group(1), 16),
            "name": m.group(3),
            "boss_arena": m.group(2) == "B",
            "door_flag": int(m.group(4) or 0),
        })
    return out


def maps(data: Path) -> list[dict]:
    src = (data / "maps.go").read_text()
    visible = src[src.index("var MapVisible"):src.index("// ── Dungeon maps")]
    fragments = dict(
        (int(a), int(b, 16))
        for a, b in re.findall(r"\t(\d+): 0x([0-9A-Fa-f]+), //", src[src.index("var MapFragmentItems"):])
    )
    out = []
    for m in re.finditer(r'(\d+): \{Name: "([^"]+)", Area: "([^"]+)"\}', visible):
        flag = int(m.group(1))
        out.append({"flag": flag, "name": m.group(2), "area": m.group(3), "fragment": fragments.get(flag)})
    return out


def bosses(data: Path) -> list[dict]:
    src = (data / "bosses.go").read_text()
    return [
        {"flag": int(a), "name": n, "region": r, "type": t}
        for a, n, r, t in re.findall(r'(\d+): \{Name: "([^"]+)", Region: "([^"]+)", Type: "([a-z]+)"', src)
    ]


def event_flag_table(data: Path) -> str:
    rows = re.findall(r"(\d+):\s*\{Byte:\s*(0x[0-9A-Fa-f]+|\d+),\s*Bit:\s*(\d+)\}", (data / "event_flags.go").read_text())
    return "\n".join(f"{a},{int(b, 0)},{c}" for a, b, c in rows) + "\n"


def main() -> None:
    data = Path(sys.argv[1]) / "backend" / "db" / "data"
    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in [("items", items(data)), ("graces", graces(data)), ("maps", maps(data)), ("bosses", bosses(data))]:
        (OUT / f"{name}.json").write_text(json.dumps(rows, indent=0, ensure_ascii=False) + "\n")
        print(f"{name}: {len(rows)}")
    (OUT / "eventflag_table.csv").write_text(event_flag_table(data))
    shutil.copy(data / "eventflag_bst.txt", OUT / "eventflag_bst.csv")


if __name__ == "__main__":
    main()
