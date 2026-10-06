"""Edits on one character slot. Never changes the slot's size.

New weapons/armor/Ashes of War reuse item-table entries that nothing references
(character-creation previews and other leftovers), keeping their handles. Every
operation appends to `log`; `validate()` must pass before the bytes are used.
"""

from __future__ import annotations

import math
import struct

from . import db
from .save import (
    H_AOW, H_ARMOR, H_GOODS, H_TALISMAN, H_WEAPON, HEADER_SIZE, SLOT_SIZE,
    ACQUIRED_CAPACITY, InvEntry, Slot, SaveError, u32,
)

MAX_RUNES = 999_999_999


class EditError(Exception):
    pass


def rune_cost(level: int) -> int:
    """Runes to go from `level` to `level + 1`."""
    x = max(((level + 81) - 92) * 0.02, 0)
    return math.floor((x + 0.1) * (level + 81) ** 2) + 1


def runes_between(a: int, b: int) -> int:
    return sum(rune_cost(lv) for lv in range(a, b))


class Editor:
    def __init__(self, data: bytearray, slot_index: int):
        self.data = data
        self.original = bytes(data)
        self.slot = Slot.parse(data, slot_index)
        self.log: list[str] = []
        self._pools: tuple[list, list, list] | None = None

    # --- orphan item-table entries ------------------------------------------------------
    def _refs(self, snapshot: bytes, handle: int, own: int) -> list[int]:
        pat, out, base = struct.pack("<I", handle), [], self.slot.base
        i = snapshot.find(pat)
        while i != -1:
            if base + i != own:
                out.append(base + i)
            i = snapshot.find(pat, i + 1)
        return out

    def _orphans(self):
        if self._pools is None:
            s = self.slot
            snap = bytes(self.data[s.base:s.base + SLOT_SIZE])
            plain, with_aow, armor = [], [], []
            for g in s.gaitems:
                if not g.handle or self._refs(snap, g.handle, g.offset):
                    continue
                if g.kind == H_WEAPON:
                    ah = s.weapon_aow_handle(g)
                    if ah == 0:
                        plain.append(g)
                    elif ah >> 28 == H_AOW:
                        ag = s.gaitem_by_handle(ah)
                        if ag and self._refs(snap, ah, ag.offset) == [g.offset + 16]:
                            with_aow.append((g, ag))
                elif g.kind == H_ARMOR:
                    armor.append(g)
            self._pools = (plain, with_aow, armor)
        return self._pools

    # --- inventory primitives -----------------------------------------------------------
    def _add_acquired(self, item_id: int) -> None:
        o = self.slot.acquired
        n = u32(self.data, o)
        if item_id in self.slot.acquired_ids():
            return
        if n >= ACQUIRED_CAPACITY:
            raise EditError("acquired-items list is full")
        struct.pack_into("<II", self.data, o + 8 + n * 8, item_id, 1)
        struct.pack_into("<i", self.data, o, n + 1)

    def _inv_append(self, handle: int, qty: int, key: bool) -> None:
        inv = self.slot.held
        if key:
            if len(inv.key) >= inv.n_key:
                raise EditError("key-item inventory is full")
            pos = inv.key_slot(len(inv.key))
        else:
            if len(inv.common) >= inv.n_common:
                raise EditError("inventory is full")
            pos = inv.common_slot(len(inv.common))
        entry_index = inv.next_acq * 2
        struct.pack_into("<3I", self.data, pos, handle, qty, entry_index)
        (inv.key if key else inv.common).append(InvEntry(handle, qty, entry_index))
        if not key:
            inv.next_equip += 1
        inv.next_acq += 1
        struct.pack_into("<I", self.data, inv.offset, len(inv.common))
        struct.pack_into("<I", self.data, inv.key_count_offset, len(inv.key))
        struct.pack_into("<2I", self.data, inv.tail_offset, inv.next_equip, inv.next_acq)

    def _held(self, handle: int):
        inv = self.slot.held
        for lst, key in ((inv.common, False), (inv.key, True)):
            for i, e in enumerate(lst):
                if e.handle == handle:
                    return key, i, e
        return None

    # --- operations -----------------------------------------------------------------------
    def set_runes(self, runes: int) -> None:
        runes = max(0, min(int(runes), MAX_RUNES))
        before = self.slot.runes
        struct.pack_into("<I", self.data, self.slot.pgd + 0x64, runes)
        self.log.append(f"runes {before:,} -> {runes:,}")

    def add_runes(self, runes: int) -> None:
        self.set_runes(self.slot.runes + int(runes))

    def runes_for_level(self, target_level: int) -> None:
        """Add exactly the runes needed to level from the current level to `target_level`."""
        need = runes_between(self.slot.level, int(target_level))
        if need <= 0:
            raise EditError(f"already level {self.slot.level}")
        self.log.append(f"level {self.slot.level} -> {target_level} costs {need:,} runes")
        self.add_runes(need)

    def set_talisman_slots(self, total: int) -> None:
        if not 1 <= total <= 4:
            raise EditError("talisman slots go from 1 to 4")
        self.data[self.slot.pgd + 0xBE] = total - 1
        self.log.append(f"talisman slots -> {total}")

    def add_item(self, item: str | int, quantity: int = 1, upgrade: int = 0,
                 affinity: str = "standard", ash_of_war: str | int | None = None,
                 category: str | None = None) -> None:
        it = db.resolve_item(item, category=category)
        kind = db.kind(it)
        if db.NEVER_OFFER & set(it["flags"]):
            raise EditError(f'{it["name"]} is flagged {it["flags"]}; refusing to add it')
        if kind == "weapon":
            for _ in range(int(quantity)):
                self._add_weapon(it, int(upgrade), affinity, ash_of_war)
        elif kind == "armor":
            for _ in range(int(quantity)):
                self._add_armor(it)
        elif kind == "aow":
            raise EditError("loose Ashes of War aren't supported yet; attach one to a weapon instead")
        elif kind == "arrow":
            raise EditError("arrows and bolts aren't supported yet")
        elif kind == "talisman":
            self._add_talisman(it)
        else:
            if it["category"] == "ashes" and upgrade:
                it = db.resolve_item(it["id"] + int(upgrade))
            self._add_goods(it, int(quantity), key=(kind == "key"))

    def _add_weapon(self, it: dict, upgrade: int, affinity: str, ash_of_war) -> None:
        maxu = it["max_upgrade"]
        if not 0 <= upgrade <= maxu:
            raise EditError(f'{it["name"]} upgrades to +{maxu} at most')
        aff = db.AFFINITIES.get(affinity.lower())
        if aff is None:
            raise EditError(f"unknown affinity {affinity!r}; one of {', '.join(db.AFFINITIES)}")
        if aff and maxu != 25:
            raise EditError(f'{it["name"]} is a unique (somber) weapon and can\'t take an affinity')
        if aff and ash_of_war is None:
            raise EditError("an affinity comes from an Ash of War: pass ash_of_war too")
        plain, with_aow, _ = self._orphans()
        item_id = it["id"] + aff + upgrade
        label = f'{affinity.title() + " " if aff else ""}{it["name"]} +{upgrade}'
        if ash_of_war is not None:
            aow = db.resolve_item(ash_of_war, category="ashes_of_war")
            if db.kind(aow) != "aow":
                raise EditError(f'{aow["name"]} is not an Ash of War')
            if not with_aow:
                raise EditError("no free item-table entry for a weapon with an Ash of War")
            g, ag = with_aow.pop(0)
            struct.pack_into("<I", self.data, ag.offset + 4, aow["id"])
            self._inv_append(ag.handle, 1, key=False)
            self._add_acquired(aow["id"])
            label += f' with {aow["name"]}'
        else:
            if not plain:
                raise EditError("no free item-table entry for a weapon")
            g = plain.pop(0)
        struct.pack_into("<I", self.data, g.offset + 4, item_id)
        self._inv_append(g.handle, 1, key=False)
        self._add_acquired(it["id"] // 10000 * 10000)
        self.log.append(f"added {label}")

    def _add_armor(self, it: dict) -> None:
        _, _, armor = self._orphans()
        if not armor:
            raise EditError("no free item-table entry for armor")
        g = armor.pop(0)
        struct.pack_into("<I", self.data, g.offset + 4, it["id"])
        self._inv_append(g.handle, 1, key=False)
        self._add_acquired(it["id"])
        self.log.append(f'added {it["name"]}')

    def _add_talisman(self, it: dict) -> None:
        handle = (H_TALISMAN << 28) | (it["id"] & 0x0FFFFFFF)
        if self._held(handle):
            raise EditError(f'{it["name"]} is already in the inventory')
        self._inv_append(handle, 1, key=False)
        self._add_acquired(it["id"])
        self.log.append(f'added {it["name"]}')

    def _add_goods(self, it: dict, qty: int, key: bool) -> None:
        handle = (H_GOODS << 28) | (it["id"] & 0x0FFFFFFF)
        cap = max(it["max_inventory"], 1)
        held = self._held(handle)
        if held:
            is_key, i, e = held
            new = min(e.quantity + qty, cap)
            inv = self.slot.held
            pos = inv.key_slot(i) if is_key else inv.common_slot(i)
            struct.pack_into("<I", self.data, pos + 4, new)
            self.log.append(f'{it["name"]}: had {e.quantity}, now {new}' + (f" (cap {cap})" if new < e.quantity + qty else ""))
            e.quantity = new
            return
        q = min(qty, cap)
        self._inv_append(handle, q, key=key)
        self._add_acquired(it["id"])
        self.log.append(f'added {q} x {it["name"]}' + (f" (capped at {cap})" if q < qty else ""))

    def set_flag(self, flag: int, value: bool = True) -> None:
        byte, bit = db.flag_position(int(flag))
        o = self.slot.event_flags + byte
        self.data[o] = (self.data[o] | (1 << bit)) if value else (self.data[o] & ~(1 << bit) & 0xFF)

    def get_flag(self, flag: int) -> bool:
        byte, bit = db.flag_position(int(flag))
        return bool(self.data[self.slot.event_flags + byte] >> bit & 1)

    def unlock_grace(self, grace: str | int) -> None:
        g = db.resolve_grace(grace)
        if g["boss_arena"]:
            raise EditError(f'{g["name"]} is inside a boss arena; unlock a grace outside it instead')
        self.set_flag(g["flag"])
        if g["door_flag"]:
            self.set_flag(g["door_flag"])
        self.log.append(f'grace unlocked: {g["name"]}')

    def unlock_map(self, region: str | int) -> None:
        m = db.resolve_map(region)
        self.set_flag(m["flag"])
        frag = db.items_by_id().get(m["fragment"])
        handle = (H_GOODS << 28) | (m["fragment"] & 0x0FFFFFFF)
        if frag and not self._held(handle):
            self._inv_append(handle, 1, key=True)
            self._add_acquired(m["fragment"])
        self.log.append(f'map revealed: {m["name"]}')

    # --- checks ---------------------------------------------------------------------------
    def validate(self) -> list[str]:
        if len(self.data) != len(self.original):
            raise EditError("file size changed")
        lo, hi = self.slot.base, self.slot.base + SLOT_SIZE
        if self.data[:lo] != self.original[:lo] or self.data[hi:] != self.original[hi:]:
            raise EditError("bytes outside the character's slot changed")
        try:
            after = Slot.parse(self.data, self.slot.index)
        except SaveError as e:
            raise EditError(f"slot no longer parses after the edit: {e}") from e
        if after.pgd != self.slot.pgd or after.event_flags != self.slot.event_flags:
            raise EditError("slot layout moved")
        changed = sum(a != b for a, b in zip(self.data[lo:hi], self.original[lo:hi]))
        return [f"{changed} bytes changed, all inside slot {self.slot.index} ({after.name})"]


def apply_operations(data: bytearray, slot_index: int, operations: list[dict]) -> Editor:
    """Run a list like [{"op": "add_item", "item": "Blasphemous Blade", "upgrade": 10}, ...]."""
    ed = Editor(data, slot_index)
    ops = {
        "set_runes": ed.set_runes, "add_runes": ed.add_runes, "runes_for_level": ed.runes_for_level,
        "set_talisman_slots": ed.set_talisman_slots, "add_item": ed.add_item,
        "unlock_grace": ed.unlock_grace, "unlock_map": ed.unlock_map,
    }
    for n, op in enumerate(operations, 1):
        op = dict(op)
        name = op.pop("op", None)
        if name not in ops:
            raise EditError(f"operation {n}: unknown op {name!r}; one of {', '.join(ops)}")
        try:
            ops[name](**op)
        except TypeError as e:
            raise EditError(f"operation {n} ({name}): {e}") from e
        except (LookupError, EditError) as e:
            raise EditError(f"operation {n} ({name}): {e}") from e
    return ed
