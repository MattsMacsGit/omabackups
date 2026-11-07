"""The data verbs (stage 3): only into this computer's own backup line.

  send BACKUP LINE PART <rsync server args>    rsync into current/LINE/PART
  fetch BACKUP POINT PART <rsync server args>  rsync out of a restore point (read only)
  apply BACKUP LINE PART                       replay renames/deletes (JSON input)
  ranges BACKUP LINE PART                      write changed ranges into one file
  reuse BACKUP LINE PART                       clone what's unchanged in a restore point
  snapshot BACKUP LINE NAME                    a restore point (point.json, changes.json input)
  info BACKUP POINT                            a restore point's point.json and changes.json
  keep / release BACKUP POINT                  kept restore points

PART is system, home or boot. Only the line's owner may write to it (D22a),
and every path stays inside the part: no "..", no following links out.
"""

import json
import os
import shutil
import stat
import struct
import sys
from pathlib import Path

import conf
import layout
import registry
import rsync_args
from host import host, mountpoint
from registry import Refused
from stream import Stream

PARTS = ("system", "home", "boot")
OWNER = ("owner",)
MAX_OPS = 16 << 20


def _my_line(call, bid: str, line: str) -> Path:
    """current/LINE of a line this key's computer owns, in an unlocked backup."""
    data = registry.load()
    registry.the_backup(data, bid, call.kid, OWNER)
    system = data["keys"][call.kid].get("system")
    if not host().is_mounted(bid):
        raise Refused("this backup is locked (unlock it first)")
    inside = mountpoint(bid)
    layout.check(inside, bid)
    for entry in layout.lines(inside):
        if entry["line"] == line:
            if entry.get("read_only"):
                raise Refused(f"backup line {line} is read only (it was handed over)")
            if entry.get("owner") != system:
                raise Refused(f"backup line {line} belongs to another computer")
            return inside / "current" / line
    raise Refused(f"no backup line {line}")


def _part(call, bid: str, line: str, part: str) -> Path:
    if part not in PARTS:
        raise Refused("the part must be system, home or boot")
    root = _my_line(call, bid, line) / part
    root.mkdir(exist_ok=True)
    return root


def _inside(root: Path, rel: str) -> Path:
    """`rel` under `root`, refusing anything that could lead out of it."""
    if not rel or rel.startswith("/") or "\0" in rel or any(
            p in ("", ".", "..") for p in rel.split("/")):
        raise Refused(f"not a path inside the backup: {rel[:80]!r}")
    path = root / rel
    real_root, real_parent = os.path.realpath(root), os.path.realpath(path.parent)
    if real_parent != real_root and not real_parent.startswith(real_root + "/"):
        raise Refused(f"that path leads out of the backup: {rel[:80]!r}")
    return path


def v_send(call):
    if len(call.args) < 7:
        raise Refused("wrong number of arguments")
    bid, line, part = call.args[:3]
    root = _part(call, bid, line, part)
    options = rsync_args.check(call.args[3:], sender=False)
    return Stream(["rsync", *options, ".", str(root) + "/"], cwd=str(root))


def v_fetch(call):
    """fetch BACKUP POINT PART <rsync server args>: read one part of a restore
    point (Browse, Restore my files, rescues, checks). Owner and rescue keys."""
    if len(call.args) < 8:
        raise Refused("wrong number of arguments")
    bid, point, part = call.args[:3]
    registry.the_backup(registry.load(), bid, call.kid, conf.ROLES)
    if part not in PARTS or not conf.POINT.match(point):
        raise Refused("that is not a restore point and part")
    if not host().is_mounted(bid):
        raise Refused("this backup is locked (unlock it first)")
    root = mountpoint(bid) / "points" / point / part
    if not root.is_dir():
        raise Refused("no such restore point")
    options = rsync_args.check(call.args[3:], sender=True)
    return Stream(["rsync", *options, ".", str(root) + "/"], cwd=str(root))


def v_browse(call):
    """browse BACKUP POINT: the restore point, read-only, over SFTP (D37:
    Browse; the computer mounts it with sshfs). Owner and rescue keys."""
    if len(call.args) != 2:
        raise Refused("wrong number of arguments")
    bid, point = call.args
    registry.the_backup(registry.load(), bid, call.kid, conf.ROLES)
    if not conf.POINT.match(point):
        raise Refused("that is not a restore point")
    if not host().is_mounted(bid):
        raise Refused("this backup is locked (unlock it first)")
    root = mountpoint(bid) / "points" / point
    if not root.is_dir():
        raise Refused("no such restore point")
    return Stream([sys.executable, os.path.abspath(sys.argv[0]), "sftp", str(root)], cwd=str(root))


def v_apply(call):
    """Input: [["rename", from, to] | ["delete", path], ...] in the order they happened."""
    if len(call.args) != 3:
        raise Refused("wrong number of arguments")
    root = _part(call, *call.args)
    try:
        ops = json.loads(call.read_input(MAX_OPS))
    except ValueError:
        raise Refused("the list of changes is damaged") from None
    done = 0
    for op in ops if isinstance(ops, list) else []:
        if op and op[0] == "rename" and len(op) == 3:
            a, b = _inside(root, op[1]), _inside(root, op[2])
            if os.path.lexists(a):
                b.parent.mkdir(parents=True, exist_ok=True)
                _inside(root, op[2])   # check again now the folders exist
                os.rename(a, b)
                done += 1
        elif op and op[0] == "delete" and len(op) == 2:
            a = _inside(root, op[1])
            if os.path.isdir(a) and not os.path.islink(a):
                shutil.rmtree(a)
                done += 1
            elif os.path.lexists(a):
                a.unlink()
                done += 1
        else:
            raise Refused("unknown change in the list")
    return {"applied": done}


_RANGE = struct.Struct(">QQ")


def v_ranges(call):
    """Input: one JSON line {"path", "size", "mode", "uid", "gid", "mtime_ns"},
    then [offset][length][bytes]... (streamed). The file's details are set
    too, so rsync never has to re-read a big file for its date alone."""
    if len(call.args) != 3:
        raise Refused("wrong number of arguments")
    root = _part(call, *call.args)
    try:
        info = json.loads(call.reader.line(4096))
        path, size = _inside(root, str(info["path"])), int(info["size"])
    except (ValueError, KeyError, TypeError):
        raise Refused("the changed ranges are damaged") from None
    fd = os.open(path, os.O_WRONLY | os.O_NOFOLLOW)
    written = 0
    try:
        while head := call.reader.read(_RANGE.size):
            if len(head) < _RANGE.size:
                head += call.reader.exactly(_RANGE.size - len(head))
            offset, length = _RANGE.unpack(head)
            while length:
                chunk = call.reader.read(min(length, 1 << 20))
                if not chunk:
                    raise Refused("the changed ranges ended early")
                os.pwrite(fd, chunk, offset)
                offset += len(chunk)
                length -= len(chunk)
                written += len(chunk)
        os.ftruncate(fd, size)
        if "mode" in info:
            if os.geteuid() == 0:   # (the test server isn't root)
                os.fchown(fd, int(info["uid"]), int(info["gid"]))
            os.fchmod(fd, int(info["mode"]) & 0o7777)
            os.utime(fd, ns=(int(info["mtime_ns"]), int(info["mtime_ns"])))
    except EOFError:
        raise Refused("the changed ranges ended early") from None
    finally:
        os.close(fd)
    return {"written": written}


def v_reuse(call):
    """reuse BACKUP LINE PART -- input: {"dirs": [path], "files": [[path, size, mtime_ns]]}.
    Never send the same data twice (D25): what the working copy lacks but a
    restore point holds unchanged (same place; for files, same size and date)
    is cloned from there (btrfs: instant, no space). rsync checks again after."""
    if len(call.args) != 3:
        raise Refused("wrong number of arguments")
    bid, line, part = call.args
    root = _part(call, bid, line, part)
    inside = root.parent.parent.parent
    try:
        asked = json.loads(call.read_input(MAX_OPS))
        dirs, files = list(asked.get("dirs", [])), list(asked.get("files", []))
    except (ValueError, AttributeError, TypeError):
        raise Refused("the list to reuse is damaged") from None
    sources = [inside / "points" / name / part for name in reversed(layout.points(inside))]
    done = {"dirs": 0, "files": 0, "bytes": 0}

    def found_in(src_root: Path, rel: str) -> Path | None:
        try:
            return _inside(src_root, rel) if src_root.is_dir() else None
        except Refused:
            return None

    for rel in dirs:
        target = _inside(root, str(rel))
        if os.path.lexists(target):
            continue
        for src_root in sources:
            src = found_in(src_root, str(rel))
            if src and src.is_dir() and not src.is_symlink():
                target.parent.mkdir(parents=True, exist_ok=True)
                host().clone(src, target)
                done["dirs"] += 1
                done["bytes"] += sum(f.stat().st_size for f in target.rglob("*")
                                     if f.is_file() and not f.is_symlink())
                break
    for entry in files:
        rel, size, mtime = str(entry[0]), int(entry[1]), int(entry[2])
        target = _inside(root, rel)
        if os.path.lexists(target):
            continue
        for src_root in sources:
            src = found_in(src_root, rel)
            try:
                info = os.lstat(src) if src else None
            except OSError:
                continue
            if info and stat.S_ISREG(info.st_mode) and info.st_size == size and info.st_mtime_ns == mtime:
                target.parent.mkdir(parents=True, exist_ok=True)
                host().clone(src, target)
                done["files"] += 1
                done["bytes"] += size
                break
    return done


def v_snapshot(call):
    if len(call.args) != 3:
        raise Refused("wrong number of arguments")
    bid, line, name = call.args
    current = _my_line(call, bid, line)
    if not conf.POINT.match(name) or not name.startswith(f"{line}-"):
        raise Refused("that is not a restore point name for this line")
    inside = current.parent.parent
    latest = layout.newest_in_line(layout.points(inside), line)
    if latest and name <= latest:
        raise Refused("a restore point must be newer than the last one")
    raw = call.read_input(8 << 20)
    try:
        given = json.loads(raw)
    except ValueError:
        raise Refused("point.json is damaged") from None
    # New style: {"point.json": {...}, "changes.json": {...}}; old style: point.json itself.
    files = given if isinstance(given, dict) and "point.json" in given else {"point.json": given}
    for fname in ("point.json", "changes.json"):
        if fname in files:
            (current / fname).write_text(json.dumps(files[fname], indent=1) + "\n")
        elif fname == "changes.json":
            (current / fname).unlink(missing_ok=True)   # never an older day's list in a new point
    host().snapshot(current, inside / "points" / name)
    return {"point": name}


def v_info(call):
    """info BACKUP POINT -- a restore point's point.json and changes.json (read only)."""
    if len(call.args) != 2:
        raise Refused("wrong number of arguments")
    bid, name = call.args
    registry.the_backup(registry.load(), bid, call.kid, conf.ROLES)
    if not conf.POINT.match(name):
        raise Refused("that is not a restore point name")
    if not host().is_mounted(bid):
        raise Refused("this backup is locked (unlock it first)")
    folder = mountpoint(bid) / "points" / name
    if not folder.is_dir():
        raise Refused("no such restore point")
    out = {}
    for fname in ("point.json", "changes.json"):
        try:
            out[fname.removesuffix(".json")] = json.loads((folder / fname).read_text())
        except (OSError, ValueError):
            out[fname.removesuffix(".json")] = None
    return out


def _kept(call, keep: bool):
    if len(call.args) != 2:
        raise Refused("wrong number of arguments")
    bid, name = call.args
    registry.the_backup(registry.load(), bid, call.kid, OWNER)
    if not host().is_mounted(bid):
        raise Refused("this backup is locked (unlock it first)")
    inside = mountpoint(bid)
    if name not in layout.points(inside):
        raise Refused("no such restore point")
    kept = layout.kept(inside)
    names = [n for n in kept["kept"] if n != name] + ([name] if keep else [])
    if not keep and name == kept.get("return_point"):
        kept["return_point"] = None
    layout.write_kept(inside, {**kept, "kept": sorted(names)})
    return {"kept": sorted(names)}


VERBS = {"send": v_send, "fetch": v_fetch, "browse": v_browse, "apply": v_apply, "reuse": v_reuse, "info": v_info, "ranges": v_ranges, "snapshot": v_snapshot,
         "keep": lambda call: _kept(call, True), "release": lambda call: _kept(call, False)}
