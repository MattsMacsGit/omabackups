"""Migrate and the handover (D22, D22a): a new computer joins a backup with
its password, reads it while it migrates, and takes it over at its first
backup.

  join             input {"password", "key"}: every backup on this server that
                   password opens; this computer gets its own key file in it
                   and may read it (role "reader") until it takes it over
  handover B P     this computer takes the backup over: a new line starts from
                   restore point P (nothing stored twice); every other line
                   becomes read-only; P is kept as the Return point; the old
                   owner can still read (Browse, bring files back)
  newline B P      a line of its own beside the others (the old computer's
                   "Set up a new backup", D22a): nobody else is changed
  rebuild B L P    line L's working copy rebuilt from restore point P (audit
                   1.7, 1.x's rebuild-current): same line, restore points
                   untouched
"""

import base64
import binascii
import json
import time

import conf
import holds
import layout
import registry
from host import host
from registry import Refused
from verbs import Call, _argc, _box, _need_open
from verbs_data import _my_line

FAILED_WAIT = 2      # seconds after a password that opened nothing (slows guessing)


def v_join(call: Call) -> dict:
    _argc(call, 0)
    data = registry.load()
    if registry.the_key(data, call.kid)["kind"] != "computer":
        raise Refused("only a computer's key can join a backup")
    try:
        given = json.loads(call.read_input(4 * conf.MAX_SECRET))
        password = given["password"].encode("utf-8")
        key = base64.b64decode(given["key"], validate=True)
    except (ValueError, KeyError, TypeError, AttributeError, binascii.Error):
        raise Refused("join needs the password and this computer's key") from None
    if not password or not key or len(password) > conf.MAX_SECRET:
        raise Refused("join needs the password and this computer's key")
    found = []
    for bid, backup in data["backups"].items():
        if backup.get("device"):
            continue                         # a backup disk on a computer: not here
        box = _box(bid)
        if not box.exists() or not host().tries_password(box, password):
            continue
        with holds.turn(bid):
            if backup["roles"].get(call.kid) is None:
                host().add_computer_key(box, password, key)
        with registry.changing() as now:
            roles = now["backups"][bid]["roles"]
            roles.setdefault(call.kid, "reader")
        found.append({"id": bid, "created": backup.get("created"), "size": backup.get("size")})
    if not found:
        time.sleep(FAILED_WAIT)
        raise Refused("that password doesn't open any backup on this server")
    return {"backups": found}


def _new_line(call: Call, takeover: bool) -> dict:
    _argc(call, 2)
    bid, point = call.args
    data = registry.load()
    registry.the_backup(data, bid, call.kid, conf.ROLES)
    key = data["keys"][call.kid]
    if key["kind"] != "computer":
        raise Refused("only a computer can back up into a line of its own")
    if not conf.POINT.match(point):
        raise Refused("that is not a restore point")
    system = key.get("system", "")
    with holds.turn(bid):
        inside = _need_open(bid)
        if point not in layout.points(inside):
            raise Refused("no such restore point")
        lines = layout.lines(inside)
        line = f"{max(int(entry['line']) for entry in lines) + 1:03d}"
        host().writable_copy(inside / "points" / point, inside / "current" / line)
        now = int(time.time())
        for entry in lines:
            if takeover or entry.get("owner") == system:
                entry["read_only"] = True          # one line in use per computer
        lines.append({"line": line, "owner": system, "from": point, "read_only": False, "started": now})
        layout._write(inside / "lines.json", {"lines": lines})
        if takeover:
            kept = layout.kept(inside)
            kept["return_point"] = point
            layout.write_kept(inside, kept)
            owner = layout.owner(inside)
            history = owner.get("history", []) + [{"from": owner.get("owner"), "to": system,
                                                   "at": now, "point": point, "line": line}]
            layout._write(inside / "owner.json", {"owner": system, "since": now, "history": history})
    with registry.changing() as now_data:
        roles = now_data["backups"][bid]["roles"]
        if takeover:
            for kid, role in list(roles.items()):
                if role == "owner" and kid != call.kid:
                    roles[kid] = "reader"            # the old computer: read only now
        roles[call.kid] = "owner"
    return {"line": line, "from": point, "return_point": point if takeover else None}


def v_handover(call: Call) -> dict:
    return _new_line(call, takeover=True)


def v_newline(call: Call) -> dict:
    return _new_line(call, takeover=False)


def v_rebuild(call: Call) -> dict:
    """A working copy that went wrong (a rescued system backed up over it,
    13 Nov 2026) starts again from a restore point. The copy is made beside
    it and swapped in, so the line is never without one."""
    _argc(call, 3)
    bid, line, point = call.args
    if not conf.POINT.match(point):
        raise Refused("that is not a restore point")
    with holds.turn(bid):
        current = _my_line(call, bid, line)
        inside = current.parent.parent
        if point not in layout.points(inside):
            raise Refused("no such restore point")
        new, old = current.with_name(f"{line}.new"), current.with_name(f"{line}.old")
        for leftover in (new, old):              # an earlier rebuild that was cut off
            if leftover.exists():
                host().delete_subvolume(leftover)
        host().writable_copy(inside / "points" / point, new)
        if current.exists():
            current.rename(old)
        new.rename(current)
        if old.exists():
            host().delete_subvolume(old)
    return {"rebuilt": line, "from": point}


VERBS = {"join": v_join, "handover": v_handover, "newline": v_newline, "rebuild": v_rebuild}
