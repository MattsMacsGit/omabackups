"""Set up a new backup (D22a): the old computer after a Migrate gets a backup
line of its own on the same server, starting from its last restore point on
its old, read-only line: nothing is sent again (the gatekeeper's newline).
Backups carry on there."""

import json

from omabackups.backup import progress, run
from omabackups.core import paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic
from omabackups.root import keys
from omabackups.where import location

NEEDS_GATE = 13      # join, handover, newline


def start_from(points: list[str], line: str, last: str | None) -> str | None:
    """This computer's last restore point on its old line: the one it backed
    up last (or was rescued from), else that line's newest."""
    mine = sorted(p for p in points if p.startswith(f"{line}-"))
    if last in mine:
        return last
    return mine[-1] if mine else None


def new_line(request: dict) -> dict:
    server = location.load()
    gate, _away = location.connect(server)
    if gate.check_version().get("gate", 0) < NEEDS_GATE:
        raise OmaError("OmaBackups on your backup server needs updating first.",
                       "Run: omabackups setup server --update (your backup is kept).", code="gate-version")
    bid, old = server["backup"], server.get("line", "001")
    hold = gate.call("unlock", bid, data=keys.read_unlock_key())["hold"]
    try:
        info = gate.call("points", bid)
        record = run.load_record()
        point = start_from(info.get("points") or [], old, record.get("last_point"))
        if not point:
            raise OmaError("This computer has no restore point to start a new backup from.",
                           "Set up backups again from the start instead.",
                           f"no restore point on line {old}", code="no-point")
        answer = gate.call("newline", bid, point)
    finally:
        try:
            gate.call("lock", bid, hold)
        except OmaError:
            pass
    write_atomic(paths.server_file(), (json.dumps({**server, "line": answer["line"]}, indent=2) + "\n").encode(),
                 0o644)
    # The new line is a copy of `point`. This computer's own snapshots match it
    # only if its last backup was that point: else the next backup checks all.
    if record.get("last_point") != point:
        record = {k: v for k, v in record.items() if k not in ("since", "skips")}
    run.save_record({**record, "last_point": point})
    progress.write({"running": False, "ok": True, "kind": "new-line", "line": answer["line"]})
    return {"line": answer["line"], "from": point}
