"""`omabackups files <point> [folder]` and `omabackups copy <point> <path>
[where]` (audit 5.2, as 1.x): look inside a restore point and get one thing
out, from a terminal (over SSH too). Read-only, the same access as Browse:
the restore point is opened, used, and closed again (unless Browse already
had it open)."""

import os
import shutil
from pathlib import Path

from omabackups.backup.check import human
from omabackups.core import rootjob
from omabackups.core.errors import OmaError
from omabackups.core.events import Events


def add(sub) -> None:
    f = sub.add_parser("files", help="list what's in a restore point (read-only)")
    f.add_argument("point")
    f.add_argument("folder", nargs="?", default="", help="a folder of your home in it (default: your home)")
    f.set_defaults(run=run_files)
    c = sub.add_parser("copy", help="copy a file or folder out of a restore point")
    c.add_argument("point")
    c.add_argument("path", help="what to copy, as in your home folder (Documents/letter.odt)")
    c.add_argument("where", nargs="?", default=".", help="where to put it (default: here)")
    c.set_defaults(run=run_copy)


class Opened:
    """The restore point, opened read-only for as long as it's needed."""

    def __init__(self, point: str):
        from omabackups.restore import browse
        before = browse.current()
        self.mine = not (before.get("ready") and before.get("point") == point
                         and Path(before.get("path") or "/nonexistent").is_dir())
        self.home = Path((rootjob.run("browse-open", {"point": point}) if self.mine else before)["path"])

    def inside(self, rel: str) -> Path:
        rel = rel.strip().removeprefix("~/").strip("/")
        path = (self.home / rel) if rel else self.home
        real, top = os.path.realpath(path), os.path.realpath(self.home)
        if real != top and not real.startswith(top + "/"):
            raise OmaError("That isn't inside the restore point's home folder.",
                           "Give a path as it is in your home folder, like Documents/letter.odt.", code="bad-path")
        if not os.path.lexists(path):
            raise OmaError(f"{rel or 'Your home folder'} isn't in that restore point.",
                           "omabackups files <restore point> [folder] lists what is.", code="not-found")
        return path

    def close(self) -> None:
        if self.mine:
            rootjob.run("browse-close", {})


def _size(path: Path) -> int:
    if not path.is_dir() or path.is_symlink():
        return path.lstat().st_size
    return sum(f.lstat().st_size for f in path.rglob("*") if not f.is_dir() or f.is_symlink())


def run_files(args, events: Events) -> int:
    opened = Opened(args.point)
    try:
        folder = opened.inside(args.folder)
        if not folder.is_dir():
            events.result({"file": args.folder, "size": folder.lstat().st_size},
                          f"{args.folder}  {human(folder.lstat().st_size)}")
            return 0
        rows = sorted(folder.iterdir(), key=lambda p: (not (p.is_dir() and not p.is_symlink()), p.name.lower()))
        listed = [{"name": p.name, "folder": p.is_dir() and not p.is_symlink(),
                   "size": None if p.is_dir() and not p.is_symlink() else p.lstat().st_size} for p in rows]
        lines = [f"{r['name']}/" if r["folder"] else f"{r['name']}  {human(r['size'])}" for r in listed]
        events.result({"folder": args.folder, "entries": listed}, "\n".join(lines) or "(empty)")
    finally:
        opened.close()
    return 0


def run_copy(args, events: Events) -> int:
    opened = Opened(args.point)
    try:
        source = opened.inside(args.path)
        where = Path(args.where).expanduser()
        dest = where / source.name if where.is_dir() else where
        if os.path.lexists(dest):
            raise OmaError(f"{dest} is already there, so nothing was copied.",
                           "Choose another place, or move that one aside first.", code="exists")
        if source.is_dir() and not source.is_symlink():
            shutil.copytree(source, dest, symlinks=True)
        else:
            shutil.copy2(source, dest, follow_symlinks=False)
        events.result({"copied": str(dest), "size": _size(dest)},
                      f"Copied to {dest} ({human(_size(dest))}). The restore point is unchanged.")
    finally:
        opened.close()
    return 0
