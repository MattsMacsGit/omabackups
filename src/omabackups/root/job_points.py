"""Root jobs on the backup itself (as root, through the gatekeeper):
keep / release a restore point (kept ones are never thinned or deleted),
delete one (to make room, D35), and change your backup's password."""

import json

from omabackups.backup import run
from omabackups.core.errors import OmaError
from omabackups.root import keys
from omabackups.where import location

POINT = run.thinning.NAME


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
    """Delete one restore point: never the newest, never a kept one (the
    gatekeeper refuses those too)."""
    point = str(request.get("point", ""))
    if not POINT.match(point):
        raise OmaError("That isn't a restore point.", code="bad-request")
    gate, bid = _open()
    hold = gate.call("unlock", bid, data=keys.read_unlock_key())["hold"]
    try:
        gate.call("delete", bid, point)
        space = gate.call("space", bid)
    finally:
        gate.call("lock", bid, hold)
    record = run.load_record()          # written after the server said yes
    points = {n: v for n, v in (record.get("point_skips") or {}).items() if n != point}
    run.save_record({**record, "point_skips": points, "space": space})
    return {"deleted": point, "space": space}


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
