"""Root jobs on the backup itself (as root, through the gatekeeper):
keep / release a restore point (kept ones are never thinned or deleted),
delete one (to make room, D35; any one, the newest and kept ones too, from
the command line: audit 1.8), rebuild the working copy from a restore point
(audit 1.7), change your backup's password, and a Rescue USB's read-only
key (5.7, D11)."""

import json

from omabackups.backup import progress, run, todo
from omabackups.core.errors import OmaError
from omabackups.root import keys
from omabackups.where import location

POINT = run.thinning.NAME
NEEDS_GATE = 16      # rebuild, and delete any restore point


def _new_enough(gate) -> None:
    if gate.call("version").get("gate", 0) < NEEDS_GATE:
        raise OmaError("OmaBackups on your backup server needs updating first.",
                       "Run: omabackups setup server --update (your backup is kept).", code="gate-version")


def _open():
    server = location.load()
    gate, _away = location.connect(server)
    gate.check_version()
    return gate, server["backup"]


def keep(request: dict) -> dict:
    point, on = str(request.get("point", "")), request.get("keep")
    if not POINT.match(point) or not isinstance(on, bool):
        raise OmaError("That isn't a restore point.", code="bad-request")
    gate, bid = _open()
    hold = gate.call("unlock", bid, data=keys.read_unlock_key())["hold"]
    try:
        gate.call("keep" if on else "release", bid, point)
        kept = gate.call("points", bid)["kept"]
    finally:
        gate.call("lock", bid, hold)
    record = run.load_record()          # written after the server said yes
    run.save_record({**record, "kept": kept.get("kept", []), "return_point": kept.get("return_point")})
    return {"kept": kept.get("kept", [])}


def delete(request: dict) -> dict:
    """Delete one restore point. Not the newest or a kept one (the
    gatekeeper refuses those too), unless the command line asked first and
    says "any" (audit 1.8)."""
    point, anyway = str(request.get("point", "")), request.get("any") is True
    if not POINT.match(point):
        raise OmaError("That isn't a restore point.", code="bad-request")
    gate, bid = _open()
    if anyway:
        _new_enough(gate)
    hold = gate.call("unlock", bid, data=keys.read_unlock_key())["hold"]
    try:
        gate.call("delete", bid, point, *(["any"] if anyway else []))
        space = gate.call("space", bid)
        info = gate.call("points", bid)
    finally:
        gate.call("lock", bid, hold)
    record = run.load_record()          # written after the server said yes
    points = {n: v for n, v in (record.get("point_skips") or {}).items() if n != point}
    run.save_record({**record, "point_skips": points, "space": space, "all_points": info["points"],
                     "kept": info["kept"].get("kept", []), "return_point": info["kept"].get("return_point")})
    return {"deleted": point, "space": space}


def rebuild(request: dict) -> dict:
    """The working copy of this computer's line, rebuilt from a restore point
    (1.x's rebuild-current). Then the computer lets go of what it knew about
    the old one: the next backup checks every file once (D49) and sends only
    what differs."""
    point = str(request.get("point", ""))
    if not POINT.match(point):
        raise OmaError("That isn't a restore point.", code="bad-request")
    with progress.only_one() as mine:
        if not mine:
            raise OmaError("A backup is running.", "Wait for it to finish, or press Stop, then try again.",
                           code="busy")
        server = location.load()
        gate, bid = _open()
        _new_enough(gate)
        line = server.get("line", "001")
        hold = gate.call("unlock", bid, data=keys.read_unlock_key())["hold"]
        try:
            gate.call("rebuild", bid, line, point)
        finally:
            gate.call("lock", bid, hold)
        record = run.load_record()      # written after the server said yes
        run.save_record({**record, "finished": False})
        for part in todo.any_unfinished():
            todo.clear(part)            # its list was made against the old copy
    return {"rebuilt": line, "from": point}


def change_password(request: dict) -> dict:
    old, new = request.get("old"), request.get("new")
    if not isinstance(old, str) or not isinstance(new, str) or not old or len(new) < 8:
        raise OmaError("The new password needs at least 8 characters.", code="bad-request")
    gate, bid = _open()
    if gate.call("version").get("gate", 0) < 10:
        raise OmaError("OmaBackups on your backup server needs updating first.",
                       "Run: omabackups setup server --update", code="gate-version")
    gate.call("password", bid, data=json.dumps({"old": old, "new": new}).encode())
    return {"changed": True}


def rescue_key(request: dict) -> dict:
    """A new Rescue USB key on the server (the last stick's taken off): the
    stick's settings, for the user's side to write onto it."""
    from omabackups.rescue import settings
    server = location.load()
    if server.get("kind") == "disk" or server.get("migrating"):
        raise OmaError("A Rescue USB needs this computer's backup on a backup server.",
                       "Set up backups to a server first (a disk rescue comes later).", code="no-server")
    gate, _bid = _open()
    return {"settings": settings.make(gate, server)}
