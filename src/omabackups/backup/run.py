"""One backup, start to end (as root; BUILD 6.1 D, D25).

1. Unlock your backup on the server (a hold).
2. For each part: a fresh read-only snapshot, then the everyday mix if the
   last backup finished and the skip list hasn't changed, else a full check.
3. A restore point on the server (point.json inside it).
4. Only then: the new snapshots become the "since" point; the old ones go.
Resume: the record says "not finished" from the start; a run that's cut off
(network, power, crash) leaves it so, and the next run checks every file:
rsync only sends what's still missing.
"""

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

from omabackups import __version__
from omabackups.backup import changes, skips, thinning
from omabackups.backup.send import Sender
from omabackups.backup.source import Snapshots, parts
from omabackups.core import ids, log, paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic
from omabackups.root import keys
from omabackups.where.server import Gate

RECORD = "backup.json"


def record_file() -> Path:
    return paths.system_state_dir() / RECORD


def load_record() -> dict:
    try:
        return json.loads(record_file().read_text())
    except (OSError, ValueError):
        return {}


def save_record(record: dict) -> None:
    write_atomic(record_file(), (json.dumps(record, indent=2) + "\n").encode(), 0o644)


def omarchy_version() -> str:
    try:
        return subprocess.run(["omarchy-version"], capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def point_name(line: str, latest: str | None) -> str:
    """<line>-<date>-<time> (D22a), always newer than the last one."""
    while True:
        name = f"{line}-{datetime.now():%Y-%m-%d-%H%M}"
        if not latest or name > latest:
            return name
        time.sleep(5)   # a backup within the same minute as the last: wait for the next


def backup(progress=lambda step, part="": None, source=None) -> dict:
    """Run one backup. `source` (tests) stands in for the snapshots and parts."""
    logger = log.get("backup")
    try:
        server = json.loads(paths.server_file().read_text())
    except (OSError, ValueError):
        raise OmaError("No backup location is set up on this computer.",
                       "Set up backups first.", code="not-set-up") from None
    gate, bid, line = Gate(server["address"]), server["backup"], server.get("line", "001")
    record = load_record()
    finished_before = record.get("finished", False)
    # From here until the end, the record says "not finished" (see Resume above).
    save_record({**record, "finished": False, "started": int(time.time())})

    progress("unlock")
    gate.check_version()
    hold = gate.call("unlock", bid, data=keys.read_unlock_key())["hold"]
    sender = Sender(gate, bid, line)
    run = datetime.now().strftime("%Y%m%dT%H%M%S")
    made, since, how = {}, dict(record.get("since", {})), {}
    fingerprints = {}
    try:
        for part in (source.parts() if source else parts()):
            skip = skips.for_part(part.name)
            fingerprints[part.name] = skip.fingerprint()
            progress("send", part.name)
            if not part.btrfs:
                sender.full(part.name, part.mount, skip)
                how[part.name] = "copied"
                continue
            snaps = source.snapshots(part) if source else Snapshots(part.device)
            with snaps:
                new = snaps.take(part, run)
                made[part.name] = new.name
                old = since.get(part.name, "")
                quick = (finished_before and snaps.exists(old)
                         and record.get("skips", {}).get(part.name) == fingerprints[part.name])
                if quick:
                    plan = changes.plan(snaps.dump(old, new), new.name, str(new), skip)
                    sender.everyday(part.name, str(new), plan)
                    how[part.name] = f"changes ({len(plan.files)} files, {len(plan.ops)} moves/deletes)"
                else:
                    sender.full(part.name, str(new), skip)
                    how[part.name] = "full check"
            gate.call("hold", bid, hold)

        progress("point")
        latest = changes_latest(gate, bid, line)
        name = point_name(line, latest)
        point = {"owner": ids.system_id(), "user": linked_user(), "omarchy": omarchy_version(),
                 "omabackups": __version__, "follows": latest, "how": how,
                 "skips": {p: skips.for_part(p).patterns for p in how}, "created": int(time.time())}
        gate.call("snapshot", bid, line, name, data=json.dumps(point).encode())
        thinned = thin(gate, bid, logger)
    except BaseException:
        # Keep the old "since" snapshots; drop the new ones. The record stays
        # "not finished", so the next backup checks every file.
        _drop(source, made)
        raise
    finally:
        try:
            gate.call("lock", bid, hold)
        except OmaError as exc:
            logger.warning("lock after backup: %s", exc.details)

    # Done: the new snapshots are the next "since" point; the old ones go.
    old = {p: n for p, n in since.items() if made.get(p) and made[p] != n}
    since.update(made)
    save_record({"finished": True, "since": since, "skips": fingerprints, "last_point": name,
                 "last_finished": int(time.time()), "how": how, "thinned": thinned})
    _drop(source, old)
    logger.info("backup %s done: %s", name, how)
    return {"point": name, "how": how}


def thin(gate: Gate, bid: str, logger) -> list[str]:
    """Smart thinning after each backup (D18). A problem here never fails the backup."""
    gone = []
    try:
        info = gate.call("points", bid)
        kept = set(info["kept"].get("kept", [])) | {info["kept"].get("return_point")}
        for old in thinning.to_delete(info["points"], datetime.now(), kept):
            gate.call("delete", bid, old)
            gone.append(old)
    except OmaError as exc:
        logger.warning("thinning: %s | %s", exc.what, exc.details)
    return gone


def changes_latest(gate: Gate, bid: str, line: str) -> str | None:
    names = [n for n in gate.call("points", bid)["points"] if n.startswith(f"{line}-")]
    return max(names) if names else None


def linked_user() -> str:
    try:
        return json.loads(paths.linked_user_file().read_text())["user"]
    except (OSError, ValueError, KeyError):
        return ""


def _drop(source, names: dict) -> None:
    """Delete local snapshots by part name -> snapshot name."""
    for part in (source.parts() if source else parts()):
        if part.name in names and part.btrfs:
            snaps = source.snapshots(part) if source else Snapshots(part.device)
            with snaps:
                snaps.drop(names[part.name])
