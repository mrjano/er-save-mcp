"""Safe edit loop: game closed -> fresh pull -> backup -> edit -> validate -> push -> read back."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from . import ps5
from .edit import Editor, apply_operations
from .save import Slot, characters, load

BACKUPS = Path(os.environ.get("ERSAVE_BACKUPS", Path.home() / ".local/share/ersave/backups"))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def pick_target(user: str | None = None) -> ps5.Target:
    targets = ps5.find_targets()
    if user:
        targets = [t for t in targets if user.lower() in (t.user.lower(), t.uid.lower())]
    if not targets:
        raise ps5.PS5Error(f"no Elden Ring PS4 save found{' for ' + user if user else ''} on the console")
    if len(targets) > 1:
        raise ps5.PS5Error("several saves found, pass user: " + ", ".join(f"{t.user} ({t.title})" for t in targets))
    return targets[0]


def pull(t: ps5.Target) -> dict[str, bytes]:
    """Every file in the mounted save (memory.dat + sce_sys/*). Read-only."""
    with ps5.mounted(t) as mp, ps5.ftp() as c:
        return ps5.ftp_get_tree(c, mp)


def _backup(t: ps5.Target, files: dict[str, bytes], label: str, meta: dict) -> Path:
    d = BACKUPS / f"{time.strftime('%Y%m%d-%H%M%S')}-{t.label}-{label}"
    for name, data in files.items():
        (d / name).parent.mkdir(parents=True, exist_ok=True)
        (d / name).write_bytes(data)
    (d / "backup.json").write_text(json.dumps({**meta, "uid": t.uid, "user": t.user, "title": t.title,
                                               "dir": t.dir, "sha": sha(files["memory.dat"])}, indent=2))
    return d


def resolve_character(data: bytearray, character: str | int) -> Slot:
    chars = characters(data)
    if isinstance(character, int) or str(character).isdigit():
        hit = [c for c in chars if c.index == int(character)]
    else:
        hit = [c for c in chars if c.name.lower() == str(character).lower()]
    if len(hit) != 1:
        listing = ", ".join(f"{c.name} (slot {c.index}, level {c.level})" for c in chars)
        raise LookupError(f"character {character!r} not found or ambiguous. Characters: {listing}")
    return hit[0]


def read(user: str | None = None) -> tuple[ps5.Target, bytearray]:
    t = pick_target(user)
    return t, load(pull(t)["memory.dat"])


def plan(character: str | int, operations: list[dict], user: str | None = None) -> dict:
    """Run the edit on a fresh copy in memory only; nothing is written to the console."""
    t, data = read(user)
    slot = resolve_character(data, character)
    ed = apply_operations(data, slot.index, operations)
    return {"character": slot.name, "slot": slot.index, "changes": ed.log, "checks": ed.validate(),
            "written": False}


def _push_verified(t: ps5.Target, data: bytes) -> None:
    with ps5.mounted(t) as mp, ps5.ftp() as c:
        ps5.ftp_put(c, f"{mp}/memory.dat", data)
    back = pull(t)["memory.dat"]
    if sha(back) != sha(data):
        raise ps5.PS5Error("read-back after writing doesn't match what was written; restore the backup")


def apply(character: str | int, operations: list[dict], user: str | None = None) -> dict:
    ps5.require_game_closed()
    t = pick_target(user)
    files = pull(t)
    data = load(files["memory.dat"])
    slot = resolve_character(data, character)
    ed: Editor = apply_operations(data, slot.index, operations)
    checks = ed.validate()
    backup = _backup(t, files, "pre-edit", {"character": slot.name, "operations": operations, "changes": ed.log})
    (backup / "edited.dat").write_bytes(bytes(ed.data))
    ps5.require_game_closed()
    _push_verified(t, bytes(ed.data))
    return {"character": slot.name, "slot": slot.index, "changes": ed.log, "checks": checks,
            "written": True, "verified": True, "backup": backup.name}


def list_backups() -> list[dict]:
    out = []
    for d in sorted(BACKUPS.glob("*/backup.json"), reverse=True):
        meta = json.loads(d.read_text())
        out.append({"id": d.parent.name, "character": meta.get("character"), "user": meta.get("user"),
                    "changes": meta.get("changes", [])})
    return out


def restore(backup_id: str) -> dict:
    d = BACKUPS / backup_id
    meta = json.loads((d / "backup.json").read_text())
    data = (d / "memory.dat").read_bytes()
    t = ps5.Target(meta["uid"], meta["user"], meta["title"], meta["dir"])
    ps5.require_game_closed()
    current = pull(t)
    _backup(t, current, "pre-restore", {"restoring": backup_id})
    _push_verified(t, data)
    return {"restored": backup_id, "user": t.user, "verified": True}
