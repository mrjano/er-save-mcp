"""Talking to the jailbroken PS5: PS5 Save Mounter payload, FTP, Payload Manager.

The mounter (n0llptr/Playstation-5-Save-Mounter, port 9090) speaks a line protocol and
unmounts when its client disconnects, so the connection is held for the whole operation.
"""

from __future__ import annotations

import ftplib
import io
import json
import os
import socket
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass

HOST = os.environ.get("ERSAVE_PS5_HOST", "192.168.1.63")
FTP_PORT = int(os.environ.get("ERSAVE_FTP_PORT", "2121"))
MOUNTER_PORT = int(os.environ.get("ERSAVE_MOUNTER_PORT", "9090"))
PAYLOAD_MANAGER = os.environ.get("ERSAVE_PAYLOAD_MANAGER", f"http://{HOST}:8084")

# Elden Ring PS4 title ids (EU, US, JP, Asia) and its save directory name
ELDEN_RING_TITLES = ("CUSA18581", "CUSA18723", "CUSA28863", "CUSA28527")
SAVE_DIR = "sce_sdmemory"


class PS5Error(Exception):
    pass


@dataclass(frozen=True)
class Target:
    uid: str          # user id, hex (e.g. "1258a7c3")
    user: str         # user name
    title: str        # CUSA...
    dir: str = SAVE_DIR

    @property
    def label(self) -> str:
        return f"{self.user}-{self.title}"


def game_running() -> bool:
    """True if a game (eboot.bin) is running. Raises if the Payload Manager can't be asked."""
    try:
        with urllib.request.urlopen(f"{PAYLOAD_MANAGER}/processes_list", timeout=6) as r:
            procs = json.loads(r.read().decode("utf-8", "replace"))["processes"]
    except Exception as e:  # noqa: BLE001 - any failure means "can't tell"
        raise PS5Error(f"can't reach the Payload Manager at {PAYLOAD_MANAGER} to check for a running game: {e}")
    return any(p.get("name") == "eboot.bin" for p in procs)


def require_game_closed() -> None:
    if game_running():
        raise PS5Error("a game is running on the PS5. Close Elden Ring completely before touching its save.")


class Mounter:
    def __init__(self):
        try:
            self.sock = socket.create_connection((HOST, MOUNTER_PORT), timeout=60)
        except OSError as e:
            raise PS5Error(
                f"PS5 Save Mounter isn't answering on {HOST}:{MOUNTER_PORT} ({e}). "
                "Load its payload on the console (it stops when the console sleeps).") from e
        self.f = self.sock.makefile("rwb")
        self.mounted: str | None = None

    def _cmd(self, line: str) -> str:
        self.f.write((line + "\n").encode())
        self.f.flush()
        reply = self.f.readline().decode().rstrip("\n")
        if not reply.startswith("OK"):
            raise PS5Error(f"mounter: {line.split()[0]} failed: {reply or 'connection closed'}")
        return reply[3:]

    def users(self) -> list[tuple[str, str]]:
        n = int(self._cmd("GET_USERS"))
        rows = [self.f.readline().decode().strip().split(" ", 1) for _ in range(n)]
        return [(r[0], r[1] if len(r) > 1 else r[0]) for r in rows]

    def mount(self, t: Target) -> str:
        self.mounted = self._cmd(f"MOUNT {t.uid} {t.title} {t.dir}")
        return self.mounted

    def umount(self) -> None:
        if self.mounted:
            self._cmd("UMOUNT")
            self.mounted = None

    def close(self) -> None:
        try:
            self.umount()
        finally:
            self.sock.close()


@contextmanager
def mounted(t: Target):
    m = Mounter()
    try:
        yield m.mount(t)
        m.umount()
    finally:
        m.close()


@contextmanager
def ftp():
    c = ftplib.FTP()
    try:
        c.connect(HOST, FTP_PORT, timeout=30)
        c.login()
    except (OSError, ftplib.Error) as e:
        raise PS5Error(f"FTP on {HOST}:{FTP_PORT} isn't answering: {e}") from e
    try:
        yield c
    finally:
        try:
            c.quit()
        except Exception:  # noqa: BLE001
            c.close()


def ftp_list(c: ftplib.FTP, path: str) -> list[tuple[str, bool]]:
    """(name, is_dir) via LIST — this server doesn't implement NLST."""
    lines: list[str] = []
    c.retrlines(f"LIST {path}", lines.append)
    out = []
    for line in lines:
        parts = line.split(None, 8)
        if len(parts) == 9 and parts[8] not in (".", ".."):
            out.append((parts[8], line.startswith("d")))
    return out


def ftp_get(c: ftplib.FTP, path: str) -> bytes:
    buf = io.BytesIO()
    c.retrbinary(f"RETR {path}", buf.write)
    return buf.getvalue()


def ftp_get_tree(c: ftplib.FTP, path: str) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for name, is_dir in ftp_list(c, path):
        if is_dir:
            files.update({f"{name}/{k}": v for k, v in ftp_get_tree(c, f"{path}/{name}").items()})
        else:
            files[name] = ftp_get(c, f"{path}/{name}")
    return files


def ftp_put(c: ftplib.FTP, path: str, data: bytes) -> None:
    c.storbinary(f"STOR {path}", io.BytesIO(data))


def find_targets() -> list[Target]:
    """Every registered user that has an Elden Ring PS4 save on the console."""
    m = Mounter()
    try:
        users = m.users()
    finally:
        m.close()
    out = []
    with ftp() as c:
        for uid, name in users:
            try:
                titles = {n for n, d in ftp_list(c, f"/user/home/{uid}/savedata") if d}
            except ftplib.Error:
                continue
            out += [Target(uid, name, t) for t in ELDEN_RING_TITLES if t in titles]
    return out
