"""MCP server: read and edit Elden Ring PS4 saves on the jailbroken PS5."""

from __future__ import annotations

from fastmcp import FastMCP

from . import db, describe, ps5, workflow
from .save import characters

mcp = FastMCP(
    "elden-ring-save",
    instructions=(
        "Edits Elden Ring PS4 saves on Jano's jailbroken PS5. Every write pulls a fresh copy, "
        "backs it up, validates the edit and verifies the read-back, so don't re-implement any "
        "of that. Elden Ring must be fully closed on the console before apply_edit or "
        "restore_backup. Use plan_edit first to show the user what will change, then apply_edit. "
        "Item names must be exact; use search_items to find them. Prefer base-game items unless "
        "the user asks for DLC ones. Boss kills are not editable on purpose."
    ),
)


@mcp.tool
def status() -> dict:
    """Is the console reachable, is the save mounter loaded, is a game running, which saves exist."""
    out: dict = {"host": ps5.HOST}
    try:
        out["game_running"] = ps5.game_running()
    except ps5.PS5Error as e:
        out["game_running"] = f"unknown: {e}"
    try:
        out["saves"] = [{"user": t.user, "uid": t.uid, "title": t.title} for t in ps5.find_targets()]
    except ps5.PS5Error as e:
        out["error"] = str(e)
    return out


@mcp.tool
def list_characters(user: str | None = None) -> list[dict]:
    """Characters in the Elden Ring save (name, slot, level, runes). Reads a fresh copy; writes nothing.
    `user` is the PS5 user name, only needed if several users have a save."""
    _, data = workflow.read(user)
    return [describe.summary(c) for c in characters(data)]


@mcp.tool
def get_character(character: str, user: str | None = None) -> dict:
    """Full view of one character (name or slot number): attributes, inventory with upgrade
    levels and Ashes of War, key items, talisman slots, unlocked graces, revealed maps,
    defeated bosses. Reads a fresh copy; writes nothing."""
    _, data = workflow.read(user)
    return describe.character(workflow.resolve_character(data, character))


@mcp.tool
def search_items(query: str, category: str | None = None, include_dlc: bool = True, limit: int = 20) -> list[dict]:
    """Find items by name. Categories: melee_armaments, ranged_and_catalysts, shields,
    arrows_and_bolts, head, chest, arms, legs, talismans, ashes_of_war, ashes (spirit ashes),
    incantations, sorceries, tools, key_items, bolstering_materials, crafting_materials, info.
    Returns exact names to use in add_item, max upgrade level and whether it's DLC."""
    return [{"name": i["name"], "category": i["category"], "max_upgrade": i["max_upgrade"],
             "max_held": i["max_inventory"], "dlc": db.is_dlc(i)}
            for i in db.search_items(query, category, include_dlc, limit)]


@mcp.tool
def search_graces(query: str) -> list[dict]:
    """Find Sites of Grace by name or region (e.g. "Mohgwyn", "Caelid")."""
    q = query.lower()
    return [{"name": g["name"], "boss_arena": g["boss_arena"]} for g in db.graces() if q in g["name"].lower()]


@mcp.tool
def list_maps() -> list[str]:
    """Map regions that unlock_map accepts."""
    return [m["name"] for m in db.maps() if m["fragment"]]


OPERATIONS_DOC = """
`operations` is a list of objects, applied in order:
- {"op": "add_item", "item": "<exact name>", "quantity": 1, "upgrade": 0,
   "affinity": "standard|heavy|keen|quality|fire|flame art|lightning|sacred|magic|cold|poison|blood|occult",
   "ash_of_war": "<name>", "category": "<to disambiguate>"}
   Weapons: upgrade up to their max (+25 regular, +10 somber). An affinity needs an Ash of
   War; somber (unique) weapons can't take one. Spirit ashes: upgrade = +N.
   Goods already held are topped up to the game's cap.
- {"op": "runes_for_level", "target_level": 150}   adds exactly the runes to get there
- {"op": "add_runes", "runes": 100000} / {"op": "set_runes", "runes": 0}
- {"op": "set_talisman_slots", "total": 4}
- {"op": "unlock_grace", "grace": "<name>"}         not boss-arena graces
- {"op": "unlock_map", "region": "<name>"}          reveals it and adds the fragment
"""


@mcp.tool(description="Preview an edit on a fresh copy of the save. Writes nothing.\n" + OPERATIONS_DOC)
def plan_edit(character: str, operations: list[dict], user: str | None = None) -> dict:
    return workflow.plan(character, operations, user)


@mcp.tool(description=(
    "Apply an edit to the save on the console: requires Elden Ring closed; pulls a fresh copy, "
    "backs it up, edits, validates, writes and verifies the read-back.\n" + OPERATIONS_DOC))
def apply_edit(character: str, operations: list[dict], user: str | None = None) -> dict:
    return workflow.apply(character, operations, user)


@mcp.tool
def list_backups() -> list[dict]:
    """Backups taken before each edit, newest first, with what each edit changed."""
    return workflow.list_backups()


@mcp.tool
def restore_backup(backup_id: str) -> dict:
    """Put a backup's save back on the console (Elden Ring must be closed). The current save is
    backed up first, so a restore can itself be undone."""
    return workflow.restore(backup_id)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
