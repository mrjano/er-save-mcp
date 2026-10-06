"""Static game data: items, graces, maps, bosses and event-flag addressing.

Generated from oisis/EldenRing-SaveForge (GPL-3.0) by tools/gen_db.py.
"""

from __future__ import annotations

import difflib
import json
import re
from functools import cache
from importlib.resources import files

from .save import EVENT_FLAGS_SIZE, T_AOW, T_ARMOR, T_GOODS, T_TALISMAN, T_WEAPON

DATA = files("ersave") / "data"

AFFINITIES = {
    "standard": 0, "heavy": 100, "keen": 200, "quality": 300, "fire": 400, "flame art": 500,
    "lightning": 600, "sacred": 700, "magic": 800, "cold": 900, "poison": 1000, "blood": 1100,
    "occult": 1200,
}

WEAPON_CATEGORIES = {"melee_armaments", "ranged_and_catalysts", "shields"}
ARMOR_CATEGORIES = {"head", "chest", "arms", "legs"}
# key_items the game keeps in the normal inventory (checked against a real save)
KEY_ITEMS_IN_COMMON = {"Memory of Grace", "Meeting Place Map", "Mirage Riddle"}
NEVER_OFFER = {"cut_content", "ban_risk"}


def _load(name: str):
    return json.loads((DATA / f"{name}.json").read_text())


@cache
def items() -> list[dict]:
    return _load("items")


@cache
def items_by_id() -> dict[int, dict]:
    return {i["id"]: i for i in items()}


@cache
def graces() -> list[dict]:
    return _load("graces")


@cache
def maps() -> list[dict]:
    return _load("maps")


@cache
def bosses() -> list[dict]:
    return _load("bosses")


def kind(item: dict) -> str:
    """weapon | armor | talisman | aow | goods | key | arrow"""
    c, prefix = item["category"], item["id"] & 0xF0000000
    if c == "arrows_and_bolts":
        return "arrow"
    if prefix == T_WEAPON:
        return "weapon"
    if prefix == T_ARMOR:
        return "armor"
    if prefix == T_TALISMAN:
        return "talisman"
    if prefix == T_AOW:
        return "aow"
    if c == "key_items" and item["name"] not in KEY_ITEMS_IN_COMMON:
        return "key"
    return "goods"


def is_dlc(item: dict) -> bool:
    return "dlc" in item["flags"]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9+]+", " ", s.lower()).strip()


def search_items(query: str, category: str | None = None, include_dlc: bool = True, limit: int = 20) -> list[dict]:
    q = _norm(query)
    pool = [i for i in items() if not NEVER_OFFER & set(i["flags"])
            and (category is None or i["category"] == category)
            and (include_dlc or not is_dlc(i))]
    exact = [i for i in pool if _norm(i["name"]) == q]
    sub = [i for i in pool if q in _norm(i["name"]) and i not in exact]
    sub.sort(key=lambda i: len(i["name"]))
    found = exact + sub
    if not found:
        names = {_norm(i["name"]): i for i in pool}
        found = [names[n] for n in difflib.get_close_matches(q, names, n=limit, cutoff=0.6)]
    return found[:limit]


def resolve_item(name_or_id: str | int, include_dlc: bool = True, category: str | None = None) -> dict:
    """One item by exact name (case-insensitive) or id; errors list close candidates."""
    if isinstance(name_or_id, int) or str(name_or_id).lower().startswith("0x") or str(name_or_id).isdigit():
        iid = int(str(name_or_id), 0)
        if iid in items_by_id():
            return items_by_id()[iid]
        raise LookupError(f"no item with id {iid:#x}")
    hits = search_items(str(name_or_id), category=category, include_dlc=include_dlc)
    exact = [i for i in hits if _norm(i["name"]) == _norm(str(name_or_id))]
    if len(exact) == 1:
        return exact[0]
    if not exact and len(hits) == 1:
        return hits[0]
    cands = ", ".join(f'"{i["name"]}" ({i["category"]})' for i in (exact or hits)[:8]) or "none"
    raise LookupError(f'"{name_or_id}" is ambiguous or unknown; pass category to narrow it. Candidates: {cands}')


def _resolve_named(rows: list[dict], query: str | int, what: str) -> dict:
    if isinstance(query, int) or str(query).isdigit():
        hit = [r for r in rows if r["flag"] == int(query)]
    else:
        q = _norm(str(query))
        hit = [r for r in rows if _norm(r["name"]) == q] or [r for r in rows if q in _norm(r["name"])]
    if len(hit) == 1:
        return hit[0]
    cands = ", ".join(f'"{r["name"]}"' for r in hit[:8]) or "none"
    raise LookupError(f'{what} "{query}" is ambiguous or unknown. Candidates: {cands}')


def resolve_grace(q: str | int) -> dict:
    return _resolve_named(graces(), q, "grace")


def resolve_map(q: str | int) -> dict:
    return _resolve_named([m for m in maps() if m["fragment"]], q, "map")


def resolve_boss(q: str | int) -> dict:
    return _resolve_named(bosses(), q, "boss")


# --- event flags -------------------------------------------------------------------------
@cache
def _flag_table() -> dict[int, tuple[int, int]]:
    rows = (l.split(",") for l in (DATA / "eventflag_table.csv").read_text().splitlines() if l)
    return {int(a): (int(b), int(c)) for a, b, c in rows}


@cache
def _flag_bst() -> dict[int, int]:
    rows = (l.split(",") for l in (DATA / "eventflag_bst.csv").read_text().splitlines() if l)
    return {int(a): int(b) for a, b in rows}


def flag_position(flag: int) -> tuple[int, int]:
    """(byte offset inside the event-flag block, bit index) — SaveForge's addressing."""
    if flag in _flag_table():
        pos = _flag_table()[flag]
    elif flag // 1000 in _flag_bst():
        i = flag % 1000
        pos = (_flag_bst()[flag // 1000] * 125 + i // 8, 7 - i % 8)
    else:
        pos = (flag // 8, 7 - flag % 8)
    if pos[0] >= EVENT_FLAGS_SIZE:
        raise LookupError(f"event flag {flag} is outside the flag block")
    return pos
