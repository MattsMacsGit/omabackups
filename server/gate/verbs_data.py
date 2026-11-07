"""The data verbs (stage 3): only into this computer's own backup line.

  send BACKUP LINE PART <rsync server args>    rsync into current/LINE/PART
  fetch BACKUP POINT PART <rsync server args>  rsync out of a restore point (read only)
  apply BACKUP LINE PART                       replay renames/deletes (JSON input)
  ranges BACKUP LINE PART                      write changed ranges into one file
  snapshot BACKUP LINE NAME                    a restore point (point.json input)
  keep / release BACKUP POINT                  kept restore points

PART is system, home or boot. Only the line's owner may write to it (D22a),
and every path stays inside the part: no "..", no following links out.
"""

import json
import os
import shutil
import struct
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
    registry.the_backup(registry.load(), bid, call.kid, ("owner", "rescue"))
    if part not in PARTS or not conf.POINT.match(point):
        raise Refused("that is not a restore point and part")
    if not host().is_mounted(bid):
        raise Refused("this backup is locked (unlock it first)")
    root = mountpoint(bid) / "points" / point / part
    if not root.is_dir():
        raise Refused("no such restore point")
    options = rsync_args.check(call.args[3:], sender=True)
    return Stream(["rsync", *options, ".", str(root) + "/"], cwd=str(root))


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
    info = call.read_input(64 * 1024)
    try:
        json.loads(info)
    except ValueError:
        raise Refused("point.json is damaged") from None
    (current / "point.json").write_bytes(info)
    host().snapshot(current, inside / "points" / name)
    return {"point": name}


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


VERBS = {"send": v_send, "fetch": v_fetch, "apply": v_apply, "ranges": v_ranges, "snapshot": v_snapshot,
         "keep": lambda call: _kept(call, True), "release": lambda call: _kept(call, False)}
