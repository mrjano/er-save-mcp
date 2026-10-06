"""PS4 Elden Ring `memory.dat`: container and character-slot layout.

Structure ported from ClayAmore/ER-Save-Editor (save_slot.rs), corrected against
real PS4 saves: 0x70 header, 8-byte acquired-item records, 0 = "no Ash of War".
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

HEADER_SIZE = 0x70
SLOT_SIZE = 0x280000
SLOT_COUNT = 10
FILE_MIN_SIZE = HEADER_SIZE + SLOT_COUNT * SLOT_SIZE

GAITEM_COUNT = 0x1400
PGD_SIZE = 0x1B0
HELD_COMMON, HELD_KEY = 0xA80, 0x180
BOX_COMMON, BOX_KEY = 0x780, 0x80
ACQUIRED_CAPACITY = 0x1B58 * 2          # 8-byte (id, 1) records
EVENT_FLAGS_SIZE = 0x1BF99F

# Gaitem handle type nibbles (top 4 bits of a handle)
H_WEAPON, H_ARMOR, H_TALISMAN, H_GOODS, H_AOW = 0x8, 0x9, 0xA, 0xB, 0xC
# Item-id type prefixes (as stored in the gaitem map / acquired list)
T_WEAPON, T_ARMOR, T_TALISMAN, T_GOODS, T_AOW = 0x0, 0x10000000, 0x20000000, 0x40000000, 0x80000000

ATTRIBUTES = ("vigor", "mind", "endurance", "strength", "dexterity", "intelligence", "faith", "arcane")


def u32(d, o: int) -> int:
    return struct.unpack_from("<I", d, o)[0]


@dataclass
class GaItem:
    index: int
    offset: int       # absolute offset in the file
    handle: int
    item_id: int
    size: int         # 8, 16 (armor) or 21 (weapon)

    @property
    def kind(self) -> int:
        return self.handle >> 28

    @property
    def is_empty(self) -> bool:
        return self.handle == 0 and self.item_id in (0, 0xFFFFFFFF)


@dataclass
class InvEntry:
    handle: int
    quantity: int
    index: int        # acquisition sort id (2 x counter)


@dataclass
class Inventory:
    offset: int       # absolute offset of the common-count field
    n_common: int
    n_key: int
    common: list[InvEntry] = field(default_factory=list)   # only the live entries
    key: list[InvEntry] = field(default_factory=list)
    next_equip: int = 0
    next_acq: int = 0

    def common_slot(self, i: int) -> int:
        return self.offset + 4 + i * 12

    @property
    def key_count_offset(self) -> int:
        return self.offset + 4 + self.n_common * 12

    def key_slot(self, i: int) -> int:
        return self.key_count_offset + 4 + i * 12

    @property
    def tail_offset(self) -> int:
        return self.key_count_offset + 4 + self.n_key * 12

    @property
    def size(self) -> int:
        return 4 + self.n_common * 12 + 4 + self.n_key * 12 + 8


def _read_inventory(d, o: int, n_common: int, n_key: int) -> Inventory:
    inv = Inventory(offset=o, n_common=n_common, n_key=n_key)
    cnt = u32(d, o)
    inv.common = [InvEntry(*struct.unpack_from("<3I", d, inv.common_slot(i))) for i in range(cnt)]
    kcnt = u32(d, inv.key_count_offset)
    inv.key = [InvEntry(*struct.unpack_from("<3I", d, inv.key_slot(i))) for i in range(kcnt)]
    inv.next_equip, inv.next_acq = struct.unpack_from("<2I", d, inv.tail_offset)
    return inv


class SaveError(Exception):
    pass


@dataclass
class Slot:
    """Offsets into one character slot. Re-parse after any change in size (we never make one)."""

    data: bytearray
    index: int
    base: int = 0
    gaitems: list[GaItem] = field(default_factory=list)
    pgd: int = 0
    held: Inventory | None = None
    box: Inventory | None = None
    acquired: int = 0
    event_flags: int = 0

    @classmethod
    def parse(cls, data: bytearray, index: int) -> "Slot":
        s = cls(data=data, index=index, base=HEADER_SIZE + index * SLOT_SIZE)
        d, o = data, s.base + 0x20
        for k in range(GAITEM_COUNT):
            h, iid = struct.unpack_from("<II", d, o)
            n = 8
            if iid != 0 and iid & 0xF0000000 == T_WEAPON:
                n = 21
            elif iid != 0 and iid & 0xF0000000 == T_ARMOR:
                n = 16
            s.gaitems.append(GaItem(k, o, h, iid, n))
            o += n
        s.pgd = o
        o += PGD_SIZE + 0xD0 + 0x58 + 0x74 + 0x58          # pgd, unk, EquipData, ChrAsm, ChrAsm2
        s.held = _read_inventory(d, o, HELD_COMMON, HELD_KEY)
        o += s.held.size
        o += 0x74 + 0x8C + 0x18                              # magic, quick items, gestures
        o += 4 + u32(d, o) * 8                               # projectiles
        o += 0x9C + 8 + 4 + 0x12F                            # equipped items, physics, face
        s.box = _read_inventory(d, o, BOX_COMMON, BOX_KEY)
        o += s.box.size
        o += 0x100                                           # gestures
        o += 4 + u32(d, o) * 4                               # regions (invasion)
        o += 0x28 + 1 + 0x40 + 0xC + 0x1008 + 0x34           # horse, unk, menu profile, trophy equip
        s.acquired = o
        o += 8 + ACQUIRED_CAPACITY * 8
        o += 0x408 + 0x1D                                    # tutorial data, unk
        s.event_flags = o
        s._check()
        return s

    def _check(self) -> None:
        d = self.data
        if self.event_flags + EVENT_FLAGS_SIZE > self.base + SLOT_SIZE:
            raise SaveError(f"slot {self.index}: layout overruns the slot")
        if not 0 < self.level <= 713 or self.level != sum(self.attributes.values()) - 79:
            raise SaveError(f"slot {self.index}: stats don't add up to the level; unknown layout")
        handles = {g.handle for g in self.gaitems if g.handle}
        for e in self.held.common + self.box.common:
            if e.handle >> 28 in (H_WEAPON, H_ARMOR, H_AOW) and e.handle not in handles:
                raise SaveError(f"slot {self.index}: inventory handle {e.handle:#x} missing from item table")
        # (fresh characters keep stale records past the count, so only the count is checked)
        if u32(d, self.acquired) > ACQUIRED_CAPACITY:
            raise SaveError(f"slot {self.index}: acquired-items count out of range")

    # --- player data -------------------------------------------------------------------
    @property
    def name(self) -> str:
        return self.data[self.pgd + 0x94:self.pgd + 0xB4].decode("utf-16le").split("\x00")[0]

    @property
    def attributes(self) -> dict[str, int]:
        return dict(zip(ATTRIBUTES, struct.unpack_from("<8I", self.data, self.pgd + 0x34)))

    @property
    def level(self) -> int:
        return u32(self.data, self.pgd + 0x60)

    @property
    def runes(self) -> int:
        return u32(self.data, self.pgd + 0x64)

    @property
    def talisman_slots(self) -> int:
        return 1 + min(self.data[self.pgd + 0xBE], 3)

    # --- acquired list / gaitems --------------------------------------------------------
    def acquired_ids(self) -> list[int]:
        return [u32(self.data, self.acquired + 8 + k * 8) for k in range(u32(self.data, self.acquired))]

    def gaitem_by_handle(self, handle: int) -> GaItem | None:
        return next((g for g in self.gaitems if g.handle == handle), None)

    def weapon_aow_handle(self, g: GaItem) -> int:
        return u32(self.data, g.offset + 16)


def active_slots(data: bytes) -> list[bool]:
    """The game's own list of slots holding a character (UserData10, right after the slots)."""
    o = HEADER_SIZE + SLOT_COUNT * SLOT_SIZE + 4 + 8 + 0x140
    o += 8 + u32(data, o + 4)                                # CSMenuSystemSaveLoad
    flags = data[o:o + SLOT_COUNT]
    if any(b > 1 for b in flags):
        raise SaveError("profile block not where expected; unknown save layout")
    return [b == 1 for b in flags]


def load(data: bytes | bytearray) -> bytearray:
    if len(data) < FILE_MIN_SIZE:
        raise SaveError(f"not a PS4 Elden Ring memory.dat ({len(data)} bytes)")
    return bytearray(data)


def characters(data: bytearray) -> list[Slot]:
    return [Slot.parse(data, i) for i, active in enumerate(active_slots(data)) if active]
