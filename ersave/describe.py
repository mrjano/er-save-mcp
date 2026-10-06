"""Human-readable views of a character slot."""

from __future__ import annotations

from . import db
from .db import AFFINITIES
from .save import H_AOW, H_ARMOR, H_GOODS, H_TALISMAN, H_WEAPON, T_GOODS, T_TALISMAN, Slot

_AFF_NAME = {v: k.title() for k, v in AFFINITIES.items()}
# "Unarmed" and the bare head/body/arms/legs pieces every character carries
PLACEHOLDERS = {110000, 0x10002710, 0x10002774, 0x100027D8, 0x1000283C}


def _name(item_id: int) -> str:
    it = db.items_by_id().get(item_id)
    return it["name"] if it else f"unknown {item_id:#x}"


def item_label(slot: Slot, handle: int) -> str:
    kind, low = handle >> 28, handle & 0x0FFFFFFF
    if kind in (H_WEAPON, H_ARMOR, H_AOW):
        g = slot.gaitem_by_handle(handle)
        if not g:
            return f"missing {handle:#x}"
        if kind == H_WEAPON:
            iid = g.item_id
            base, aff, up = iid // 10000 * 10000, iid % 10000 // 100 * 100, iid % 100
            label = (f"{_AFF_NAME.get(aff, aff)} " if aff else "") + _name(base) + (f" +{up}" if up else "")
            ah = slot.weapon_aow_handle(g)
            ag = slot.gaitem_by_handle(ah) if ah else None
            return label + (f" [{_name(ag.item_id)}]" if ag else "")
        return _name(g.item_id)
    if kind == H_TALISMAN:
        return _name(T_TALISMAN | low)
    if kind == H_GOODS:
        return _name(T_GOODS | low)
    return f"{handle:#x}"


def summary(slot: Slot) -> dict:
    return {"slot": slot.index, "name": slot.name, "level": slot.level, "runes": slot.runes}


def flag(slot: Slot, flag_id: int) -> bool:
    byte, bit = db.flag_position(flag_id)
    return bool(slot.data[slot.event_flags + byte] >> bit & 1)


def character(slot: Slot) -> dict:
    def flags(f: int) -> bool:
        return flag(slot, f)

    inv = slot.held
    inventory: dict[str, list] = {"weapons": [], "armor": [], "talismans": [], "ashes_of_war": [], "items": []}
    bucket = {H_WEAPON: "weapons", H_ARMOR: "armor", H_TALISMAN: "talismans", H_AOW: "ashes_of_war",
              H_GOODS: "items"}
    for e in inv.common:
        b = bucket.get(e.handle >> 28)
        g = slot.gaitem_by_handle(e.handle) if b in ("weapons", "armor") else None
        if g and g.item_id in PLACEHOLDERS:
            continue
        if b:
            label = item_label(slot, e.handle)
            inventory[b].append(f"{label} x{e.quantity}" if e.quantity > 1 else label)
    return {
        **summary(slot),
        "attributes": slot.attributes,
        "talisman_slots": slot.talisman_slots,
        "inventory": inventory,
        "key_items": [item_label(slot, e.handle) + (f" x{e.quantity}" if e.quantity > 1 else "") for e in inv.key],
        "graces": [g["name"] for g in db.graces() if flags(g["flag"])],
        "maps": [m["name"] for m in db.maps() if m["fragment"] and flags(m["flag"])],
        "bosses_defeated": [b["name"] for b in db.bosses() if flags(b["flag"])],
    }
