"""The full backup's to-do list (D49 C): it checks once, then knows.

A full backup (the first one, or after the "since" snapshots were lost)
starts with one dry run against the backup server. Its list of what would be
sent, each with its size, and of what would be deleted there, is saved here
with the snapshot it was made from. The copy then sends exactly that list,
and rsync's log on this computer ticks each item off as it finishes.

Cut off (sleep, a flat battery, no network), the next run doesn't check
over the network again: btrfs says what changed between the list's snapshot
and the new one (seconds), and the new list is what's still unticked plus
what changed (carry()). One list per part, only while a full backup is
unfinished; finished, it's deleted, and everyday backups carry on.

Files: <state>/sending/<part>/meta.json, todo (NUL-separated "size<TAB>path"),
done.log (rsync's --log-file).
"""

import json
import os
import re
import shutil
import time
from pathlib import Path

from omabackups.core import paths
from omabackups.core.state import write_atomic

MARK = "OMA|"                 # our lines in rsync's output and log
OUT_FORMAT = MARK + "%i|%l|%n"
LOG_FORMAT = MARK + "%n"
_ESC = re.compile(rb"\\#(\d{3})")


def folder(part: str) -> Path:
    return paths.system_state_dir() / "sending" / part


def unescape(raw: bytes) -> str:
    """rsync writes control characters in names as \\#ooo (octal)."""
    return _ESC.sub(lambda m: bytes([int(m.group(1), 8)]), raw).decode("utf-8", "surrogateescape")


def _clean(path: str) -> str:
    path = path.rstrip("/")
    return "" if path in ("", ".") else path


def parse_check(out: bytes) -> tuple[list[tuple[str, int]], list[str]]:
    """The dry run's output -> (items to send with their data size, deletes)."""
    items, deletes = [], []
    for line in out.split(b"\n"):
        at = line.find(MARK.encode())
        if at < 0:
            continue
        fields = line[at + len(MARK):].split(b"|", 2)
        if len(fields) != 3:
            continue
        change, length, name = fields[0].strip(), fields[1], unescape(fields[2])
        path = _clean(name)
        if not path:
            continue
        if change.startswith(b"*deleting"):
            deletes.append(path)
        elif change[:1] in (b"<", b">"):                      # file data ("<": to the server)
            items.append((path, int(length or 0)))
        else:                                                 # folders, links, details
            items.append((path, 0))
    return items, deletes


def ticked(part: str) -> set[str]:
    """What rsync's log says has gone (every run of this list)."""
    log = folder(part) / "done.log"
    try:
        raw = log.read_bytes()
    except OSError:
        return set()
    out = set()
    for line in raw.split(b"\n"):
        at = line.find(b"] " + MARK.encode())
        if at >= 0:
            path = _clean(unescape(line[at + 2 + len(MARK):]))
            if path:
                out.add(path)
    return out


def save(part: str, meta: dict, items: list[tuple[str, int]]) -> None:
    """A new list (its log starts empty). Written whole, then switched in."""
    where = folder(part)
    where.mkdir(parents=True, exist_ok=True)
    data = b"".join(f"{size}\t{path}".encode("utf-8", "surrogateescape") + b"\0" for path, size in items)
    write_atomic(where / "todo", data, 0o600)
    (where / "done.log").unlink(missing_ok=True)
    meta = {**meta, "items": len(items), "bytes": sum(s for _, s in items), "made": int(time.time())}
    write_atomic(where / "meta.json", (json.dumps(meta, indent=2) + "\n").encode(), 0o600)


def load(part: str) -> tuple[dict, list[tuple[str, int]]] | None:
    where = folder(part)
    try:
        meta = json.loads((where / "meta.json").read_text())
        raw = (where / "todo").read_bytes()
    except (OSError, ValueError):
        return None
    items = []
    for entry in raw.split(b"\0"):
        if entry:
            size, _, path = entry.partition(b"\t")
            items.append((path.decode("utf-8", "surrogateescape"), int(size or 0)))
    return meta, items


def remaining(part: str) -> list[tuple[str, int]]:
    loaded = load(part)
    if not loaded:
        return []
    done = ticked(part)
    return [(p, s) for p, s in loaded[1] if p not in done]


def fits(meta: dict | None, backup: str, line: str, fingerprint: str) -> bool:
    """The list belongs to this backup, line and skip list."""
    return bool(meta) and meta.get("backup") == backup and meta.get("line") == line \
        and meta.get("fingerprint") == fingerprint


def _renamed(path: str, ops: list) -> str | None:
    """Where `path` is after the renames and deletes, in order (None: gone)."""
    for op in ops:
        if op[0] == "rename":
            a, b = op[1], op[2]
            if path == a or path.startswith(a + "/"):
                path = b + path[len(a):]
        elif op[0] == "delete":
            if path == op[1] or path.startswith(op[1] + "/"):
                return None
    return path


def carry(left: list[tuple[str, int]], plan, snapshot: str) -> list[tuple[str, int]]:
    """The new list after a cut-off: what's still unticked (followed through
    renames, dropped if deleted) plus what changed since (plan: the btrfs
    changes between the list's snapshot and `snapshot`). Sizes from `snapshot`."""
    wanted = {}
    for path, _ in left:
        moved = _renamed(path, plan.ops)
        if moved:
            wanted[moved] = None
    for path in [*plan.files, *plan.ranges]:
        wanted[path] = None
    out = []
    for path in sorted(wanted):
        full = os.path.join(snapshot, path)
        try:
            info = os.lstat(full)
        except OSError:
            continue                                   # gone since
        out.append((path, info.st_size if os.path.isfile(full) and not os.path.islink(full) else 0))
    return out


def clear(part: str) -> None:
    shutil.rmtree(folder(part), ignore_errors=True)


def any_unfinished() -> list[str]:
    root = paths.system_state_dir() / "sending"
    try:
        return sorted(p.name for p in root.iterdir() if (p / "meta.json").exists())
    except OSError:
        return []
