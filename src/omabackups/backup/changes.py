"""What changed since the last backup, from btrfs (D25, "the improved mix").

`btrfs send --no-data -p SINCE NEW | btrfs receive --dump` lists every change
between two snapshots in about a second, whatever the number of files. From
it comes a plan for one part:
- ops: renames and deletes, replayed on the server (a moved folder costs nothing);
- ranges: big files that changed a little: only the changed byte ranges;
- files: everything else that changed: sent by rsync.
Ported from the stage 0 test (proven on real data), plus the ranges.
"""

import os
import re
from dataclasses import dataclass, field

from omabackups.backup.skips import Skips

RANGES_FROM = 64 << 20      # files at least this big may go as changed ranges...
RANGES_UPTO = 0.5           # ...when less than half of them changed

TEMP = re.compile(r"^o\d+-\d+-\d+$")
LINE = re.compile(r"(\S+)\s+(\./(?:\\.|[^\s\\])*)\s*(.*)")    # escaped spaces stay in the path
DEST = re.compile(r"dest=(\./(?:\\.|[^\s\\])*)")
EXTENT = re.compile(r"offset=(\d+)\s+len=(\d+)")
WHOLE = ("clone", "write", "encoded_write", "fallocate", "fileattr", "enable_verity")
# Changes to a file's details, not its contents: rsync sends a few bytes for
# them, so they don't count towards the size (a file whose owner changed was
# counted whole: 1.4 GB for a rescue image after a rescue).
DETAILS = ("chown", "chmod", "utimes", "set_xattr", "remove_xattr")


@dataclass
class Plan:
    ops: list = field(default_factory=list)       # ["rename", a, b] / ["delete", a]
    files: list = field(default_factory=list)     # paths for rsync
    fresh: list = field(default_factory=list)     # of those, the ones new since the last backup
    light: list = field(default_factory=list)     # of those, only their details changed (owner, dates)
    ranges: dict = field(default_factory=dict)    # path -> [(offset, length), ...]


def unesc(p: str) -> str:
    """Undo the dump's escapes (\\ooo octal bytes, backslash before spaces)."""
    b = p.encode("utf-8", "surrogateescape")
    b = re.sub(rb"\\(\d{3}|.)", lambda m: bytes([int(m.group(1), 8)]) if m.group(1).isdigit()
               else m.group(1), b)
    return b.decode("utf-8", "surrogateescape")


def parse(text: str, name: str):
    """Read a dump: (changed paths, ops in stream order, extents, new paths)."""
    head = f"./{name}"

    def rel(p: str) -> str | None:
        p = unesc(p)
        if p == head:
            return None
        return p[len(head) + 1:] if p.startswith(head + "/") else p[2:]

    def moved(mapping: dict, src: str, dst: str) -> dict:
        out = {}
        for k, v in mapping.items():
            if k == src or k.startswith(src + "/"):
                out[dst + k[len(src):]] = v
            else:
                out[k] = v
        return out

    changed: set[str] = set()
    # Every folder that has something under it in the sets below. A rename of
    # anything else (each new file arrives under a temporary name and is then
    # renamed) moves one entry, not a search of everything: with 23,000 new
    # files that search took minutes (stage 8 rehearsal).
    parents: set[str] = set()

    def note(p: str) -> None:
        while "/" in p:
            p = p.rsplit("/", 1)[0]
            if p in parents:
                break                  # its own parents are in already
            parents.add(p)

    ops: list[list[str]] = []
    extents: dict[str, list] = {}
    new: set[str] = set()              # made since the last backup: whole file
    details: set[str] = set()          # only their details changed, not their contents
    on_server: set[str] = set()

    def temp_root(p: str) -> str | None:
        parts = p.split("/")
        for i, c in enumerate(parts):
            if TEMP.match(c):
                return "/".join(parts[:i + 1])
        return None

    for line in text.splitlines():
        m = LINE.match(line)
        if not m or m.group(1) in ("snapshot", "subvol"):
            continue
        cmd, path, rest = m.group(1), rel(m.group(2)), m.group(3)
        if path is None:
            continue
        if cmd == "rename":
            dest = rel(DEST.search(rest).group(1))
            if path in parents:            # a folder with things in it: move them all
                inside = {c for c in changed if c == path or c.startswith(path + "/")}
                changed -= inside
                changed |= {dest + c[len(path):] for c in inside}
                extents = moved(extents, path, dest)
                new = set(moved(dict.fromkeys(new), path, dest))
                details = set(moved(dict.fromkeys(details), path, dest))
                for c in list(changed) + list(new) + list(extents):
                    if c == dest or c.startswith(dest + "/"):
                        note(c)
            else:                          # one thing: move just it
                if path in changed:
                    changed.discard(path)
                    changed.add(dest)
                if path in extents:
                    extents[dest] = extents.pop(path)
                if path in new:
                    new.discard(path)
                    new.add(dest)
                if path in details:
                    details.discard(path)
                    details.add(dest)
                note(dest)
            src_t = temp_root(path)
            if src_t is None or src_t in on_server:
                ops.append(["rename", path, dest])
                if src_t is not None and src_t == path:
                    on_server.discard(path)
                if (dt := temp_root(dest)) is not None:
                    on_server.add(dt)
            if TEMP.match(os.path.basename(path)):
                changed.add(dest)
                note(dest)
        elif cmd in ("unlink", "rmdir"):
            changed.discard(path)
            extents.pop(path, None)
            t = temp_root(path)
            if t is None or t in on_server:
                ops.append(["delete", path])
        else:
            if cmd in DETAILS:
                if path not in changed:
                    details.add(path)      # nothing else changed it (yet)
            else:
                details.discard(path)
            changed.add(path)
            note(path)
            if cmd in ("mkfile", "mkdir", "mknod", "mkfifo", "mksock", "symlink", "link"):
                new.add(path)
            elif cmd == "update_extent" and (e := EXTENT.search(rest)):
                extents.setdefault(path, []).append((int(e.group(1)), int(e.group(2))))
            elif cmd in WHOLE:
                new.add(path)          # can't send this one as ranges
    return changed, ops, extents, new, details


def plan(text: str, name: str, snapshot: str, skips: Skips) -> Plan:
    """The plan for one part, with the skip list applied (any file or folder)."""
    changed, ops, extents, new, details = parse(text, name)
    out = Plan()
    for op in ops:
        if op[0] == "delete":
            out.ops.append(op)          # harmless if it was never there
        elif skips.skipped(op[1]) and skips.skipped(op[2]):
            continue
        elif skips.skipped(op[2]):
            out.ops.append(["delete", op[1]])   # moved into a skipped place
        elif skips.skipped(op[1]):
            # Moved out of a skipped place: the server never had it; send it all.
            moved_out = {op[2]} | _walk(snapshot, op[2])
            changed |= moved_out
            new |= moved_out
        else:
            out.ops.append(op)
    for path in sorted(changed):
        if not path or skips.skipped(path) or not os.path.lexists(os.path.join(snapshot, path)):
            continue
        full = os.path.join(snapshot, path)
        spans = extents.get(path)
        if (spans and path not in new and os.path.isfile(full) and not os.path.islink(full)
                and os.path.getsize(full) >= RANGES_FROM
                and sum(n for _, n in spans) < RANGES_UPTO * os.path.getsize(full)):
            out.ranges[path] = _merge(spans)
        else:
            out.files.append(path)
            if path in new:
                out.fresh.append(path)
            elif path in details:
                out.light.append(path)
    return out


def _walk(snapshot: str, rel: str) -> set[str]:
    found = set()
    for root, dirs, files in os.walk(os.path.join(snapshot, rel)):
        for name in dirs + files:
            found.add(os.path.relpath(os.path.join(root, name), snapshot))
    return found


def _merge(spans: list) -> list:
    out = []
    for offset, length in sorted(spans):
        if out and offset <= out[-1][0] + out[-1][1]:
            end = max(out[-1][0] + out[-1][1], offset + length)
            out[-1] = (out[-1][0], end - out[-1][0])
        else:
            out.append((offset, length))
    return out


def changed_folders(plan: Plan) -> list[str]:
    """The folders an everyday backup changed, for the Pi's size list
    (audit 5.4): each sent file's folder, and both ends of every move or
    delete. The Pi measures those (and the folders above them) again."""
    out = set()
    for path in list(plan.files) + list(plan.ranges):
        out.add(path.rpartition("/")[0])
    for op in plan.ops:
        for path in op[1:]:
            out.add(path.rpartition("/")[0])
    return sorted(out)

