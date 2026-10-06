# 0001 — Reuse orphaned item-table entries; never resize a slot

**Status:** accepted (2026-10-06)

## Context
Adding a weapon or armor needs an entry in the slot's item table (`GaItem`), whose
entries are variable-sized (8 bytes empty, 16 armor, 21 weapon). ER-Save-Editor grows
the table and pads the slot back to 0x280000 with zeros. On real PS4 saves the slot is
**full to the last byte** with live data after the parts we understand, so growing the
table pushes data off the end.

## Decision
Never change a slot's size. New weapons, armor and Ashes of War take over item-table
entries that nothing in the slot references (character-creation previews and other
leftovers), keeping the existing handle and only changing the item id. Orphans are
found fresh on every edit, because the game renumbers the table between sessions.

## Consequences
- An edit can fail with "no free item-table entry" on a character that has none left.
- Weapons with an Ash of War need an orphan weapon whose attached AoW entry is also
  referenced only by it.
- Every edit is checked: same size, nothing outside the slot changed, slot still parses,
  every inventory handle resolves.
