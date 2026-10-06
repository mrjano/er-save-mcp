# er-save-mcp

MCP server (and Python library) to read and edit **Elden Ring PS4 saves** (`memory.dat`)
on a jailbroken PS5, through the PS5 Save Mounter payload and the console's FTP server.

- `ersave/save.py` — container and character-slot layout
- `ersave/edit.py` — edits (runes, items, talisman slots, graces, maps) that never resize a slot ([ADR 0001](adr/0001-reuse-orphan-gaitems-never-resize.md))
- `ersave/db.py` — items, graces, maps, bosses and event-flag addressing
- `ersave/ps5.py` — transport: mount/unmount, FTP, game-running check
- `ersave/server.py` — the MCP tools

Data in `ersave/data/` is generated from [oisis/EldenRing-SaveForge](https://github.com/oisis/EldenRing-SaveForge)
(GPL-3.0) with `tools/gen_db.py`; the slot structure follows
[ClayAmore/ER-Save-Editor](https://github.com/ClayAmore/ER-Save-Editor), corrected for PS4.
Licensed GPL-3.0-or-later.

Tests replay real edits against local save backups (never committed):
`ERSAVE_FIXTURES=~/.local/share/ps5-jb/saves uv run pytest`.
