"""ersave — command line for the same operations as the MCP server.

  ersave status
  ersave list [--user U] [--file memory.dat]
  ersave show CHARACTER [--user U] [--file memory.dat]
  ersave plan CHARACTER OPS.json [--user U] [--file memory.dat]
  ersave apply CHARACTER OPS.json [--user U]
  ersave backups
  ersave restore BACKUP_ID
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import describe, workflow
from .edit import apply_operations
from .save import characters, load


def _data(args):
    if args.file:
        return load(Path(args.file).read_bytes())
    return workflow.read(args.user)[1]


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="ersave", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["status", "list", "show", "plan", "apply", "backups", "restore"])
    p.add_argument("args", nargs="*")
    p.add_argument("--user")
    p.add_argument("--file", help="work on a local memory.dat instead of the console (list/show/plan)")
    a = p.parse_args(argv)
    from . import server

    if a.command == "status":
        out = server.status()
    elif a.command == "list":
        out = [describe.summary(c) for c in characters(_data(a))]
    elif a.command == "show":
        out = describe.character(workflow.resolve_character(_data(a), a.args[0]))
    elif a.command == "plan":
        ops = json.loads(Path(a.args[1]).read_text())
        if a.file:
            data = _data(a)
            slot = workflow.resolve_character(data, a.args[0])
            ed = apply_operations(data, slot.index, ops)
            out = {"character": slot.name, "changes": ed.log, "checks": ed.validate(), "written": False}
        else:
            out = workflow.plan(a.args[0], ops, a.user)
    elif a.command == "apply":
        out = workflow.apply(a.args[0], json.loads(Path(a.args[1]).read_text()), a.user)
    elif a.command == "backups":
        out = workflow.list_backups()
    else:
        out = workflow.restore(a.args[0])
    json.dump(out, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
