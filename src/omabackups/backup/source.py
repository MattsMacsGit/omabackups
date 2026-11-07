"""What gets backed up on this computer, read from snapshots (as root).

system = the btrfs subvolume at /, home = the one at /home: each is read
from a read-only snapshot, so the copy is consistent while you work. One
snapshot per part stays between backups (the "since" point the change list
is worked out from, D25). boot = /boot (not btrfs): copied as it is.
Snapshots live in their own subvolume, @omabackups, at the top of the disk.
"""

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from omabackups.core import paths
from omabackups.core.errors import OmaError

SNAPSHOTS = "@omabackups"
PARTS = (("system", "/"), ("home", "/home"), ("boot", "/boot"))


def _run(*cmd: str) -> str:
    done = subprocess.run(list(cmd), capture_output=True, text=True)
    if done.returncode != 0:
        raise OmaError(f"OmaBackups couldn't prepare this computer's files ({cmd[0]} {cmd[1]}).",
                       "Try again. If it keeps failing, report it with the details.",
                       f"{' '.join(cmd)}: {done.stderr.strip()}", code="source-failed")
    return done.stdout


@dataclass
class Part:
    name: str
    mount: str
    btrfs: bool
    device: str = ""
    subvol: str = ""


def parts() -> list[Part]:
    out = []
    for name, mount in PARTS:
        found = subprocess.run(["findmnt", "-J", "-o", "SOURCE,FSTYPE,OPTIONS", "--mountpoint", mount],
                               capture_output=True, text=True)
        if found.returncode != 0 or not found.stdout.strip():
            continue    # e.g. no separate /home: it's inside system
        info = json.loads(found.stdout)
        fs = info["filesystems"][0]
        if fs["fstype"] == "btrfs":
            device = fs["source"].split("[")[0]
            subvol = next((o.split("=", 1)[1] for o in fs["options"].split(",")
                           if o.startswith("subvol=")), "/")
            out.append(Part(name, mount, True, device, subvol))
        else:
            out.append(Part(name, mount, False))
    return out


class Snapshots:
    """The snapshots of one btrfs disk, through its top level (as root)."""

    def __init__(self, device: str):
        self.device = device
        self.top = paths.system_run_dir() / "top" / device.strip("/").replace("/", "-")

    def __enter__(self):
        self.top.mkdir(parents=True, exist_ok=True)
        if not os.path.ismount(self.top):
            _run("mount", "-o", "subvolid=5,noatime", self.device, str(self.top))
        if not (self.top / SNAPSHOTS).exists():
            _run("btrfs", "subvolume", "create", str(self.top / SNAPSHOTS))
        return self

    def __exit__(self, *exc):
        subprocess.run(["umount", str(self.top)], capture_output=True)

    def path(self, name: str) -> Path:
        return self.top / SNAPSHOTS / name

    def take(self, part: Part, run: str) -> Path:
        target = self.path(f"{part.name}-{run}")
        n = 1
        while target.exists():   # never reuse a name: it could be the "since" snapshot
            n += 1
            target = self.path(f"{part.name}-{run}-{n}")
        _run("btrfs", "subvolume", "snapshot", "-r", str(self.top / part.subvol.lstrip("/")),
             str(target))
        return target

    def exists(self, name: str) -> bool:
        return bool(name) and self.path(name).is_dir()

    def dump(self, since: str, new: Path) -> str:
        """btrfs's list of changes from `since` to `new` (no file data)."""
        send = subprocess.Popen(["btrfs", "send", "-q", "--no-data", "-p", str(self.path(since)),
                                 str(new)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        done = subprocess.run(["btrfs", "receive", "--dump"], stdin=send.stdout,
                              capture_output=True, text=True, errors="surrogateescape")
        send.stdout.close()
        error = send.stderr.read().decode("utf-8", "replace")
        if send.wait() != 0 or done.returncode != 0:
            raise OmaError("OmaBackups couldn't work out what changed since the last backup.",
                           "The next backup checks every file instead.",
                           (error + done.stderr).strip(), code="changes-failed")
        return done.stdout

    def drop(self, name: str) -> None:
        if name and self.path(name).exists():
            subprocess.run(["btrfs", "subvolume", "delete", str(self.path(name))], capture_output=True)

    def nested(self, part: Part) -> list[str]:
        """Subvolumes inside this part that hold something: a snapshot can't
        include them, so they aren't backed up (paths relative to the part)."""
        done = subprocess.run(["btrfs", "subvolume", "list", "-o",
                               str(self.top / part.subvol.lstrip("/"))], capture_output=True, text=True)
        found, base = [], part.subvol.strip("/") + "/"
        for line in done.stdout.splitlines():
            path = line.split(" path ", 1)[-1].strip()
            rel = path[len(base):] if path.startswith(base) else ""
            try:
                if rel and any(os.scandir(self.top / path)):
                    found.append(rel)
            except OSError:
                pass
        return sorted(found)

    def names(self) -> list[str]:
        try:
            return sorted(p.name for p in (self.top / SNAPSHOTS).iterdir())
        except FileNotFoundError:
            return []
