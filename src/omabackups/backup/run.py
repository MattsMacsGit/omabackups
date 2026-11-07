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
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

from omabackups import __version__
from omabackups.backup import changes, check, health, schedule, skips, thinning
from omabackups.backup.send import Sender
from omabackups.backup.source import Snapshots, parts
from omabackups.core import ids, log, paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic
from omabackups.root import keys
from omabackups.where import network
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


def backup(progress=lambda step, part="": None, source=None, anyway: bool = False) -> dict:
    """Run one backup. `anyway`: the answer "Back up now" to the away limit.
    `source` (tests) stands in for this computer's parts and snapshots."""
    logger = log.get("backup")
    try:
        server = json.loads(paths.server_file().read_text())
    except (OSError, ValueError):
        raise OmaError("No backup location is set up on this computer.",
                       "Set up backups first.", code="not-set-up") from None
    address, away = network.route(server)
    gate, bid, line = Gate(address), server["backup"], server.get("line", "001")

    progress("unlock")
    gate.check_version()
    if not away:
        network.learn_away_addresses(gate, server)
    record = load_record()
    try:
        verdict = health.refresh(gate, bid)
    except OmaError as exc:
        logger.warning("health verdict: %s", exc.details)
        verdict = {}
    resend = health.resend_needed(verdict, record)    # damaged files go again, all of them
    hold = gate.call("unlock", bid, data=keys.read_unlock_key())["hold"]
    sender = Sender(gate, bid, line, compress=away)     # D25: zstd only when away
    run = datetime.now().strftime("%Y%m%dT%H%M%S")
    made, since, how, fingerprints, work, opened = {}, dict(record.get("since", {})), {}, {}, [], {}
    stack = ExitStack()
    try:
        # 1. Check first: snapshots and change lists for every part, and the size.
        progress("check")
        needed, known, left_out = 0, True, []
        for part in (source.parts() if source else parts()):
            skip = skips.for_part(part.name)
            fingerprints[part.name] = skip.fingerprint()
            if not part.btrfs:
                work.append((part, skip, None, None))
                needed += check.folder_size(part.mount)
                continue
            snaps = stack.enter_context(source.snapshots(part) if source else Snapshots(part.device))
            opened[part.name] = snaps
            new = snaps.take(part, run)
            made[part.name] = new.name
            left_out += [f"{part.mount.rstrip('/')}/{rel}" for rel in snaps.nested(part)
                         if not skip.skipped(rel)]
            old = since.get(part.name, "")
            if (not resend and record.get("finished") and snaps.exists(old)
                    and record.get("skips", {}).get(part.name) == fingerprints[part.name]):
                plan = changes.plan(snaps.dump(old, new), new.name, str(new), skip)
                needed += check.size_of(plan, str(new))
                work.append((part, skip, new, plan))
            else:
                known = False
                work.append((part, skip, new, None))
        limit = schedule.user_settings(linked_user())["away.limit_mb"]
        check.away_limit(away, anyway, needed if known else None, limit)
        if known:
            check.make_room(gate, bid, needed, logger)

        # 2. Send. From here until the end, the record says "not finished".
        save_record({**record, "finished": False, "started": int(time.time())})
        for part, skip, new, plan in work:
            progress("send", part.name)
            if new is None:
                sender.full(part.name, part.mount, skip)
                how[part.name] = "copied"
            elif plan is not None:
                sender.everyday(part.name, str(new), plan)
                how[part.name] = f"changes ({len(plan.files)} files, {len(plan.ops)} moves/deletes)"
            else:
                sender.full(part.name, str(new), skip, checksum=resend)
                how[part.name] = "full check, every file's contents" if resend else "full check"
            gate.call("hold", bid, hold)

        # 3. The restore point, then thinning.
        progress("point")
        latest = changes_latest(gate, bid, line)
        name = point_name(line, latest)
        point = {"owner": ids.system_id(), "user": linked_user(), "omarchy": omarchy_version(),
                 "omabackups": __version__, "follows": latest, "how": how, "away": away,
                 "not_included": left_out,
                 "skips": {p: skips.for_part(p).patterns for p in how}, "created": int(time.time())}
        gate.call("snapshot", bid, line, name, data=json.dumps(point).encode())
        thinned = thin(gate, bid, logger)

        # 4. Done: the new snapshots are the next "since" point; the old ones go.
        old = {p: n for p, n in since.items() if made.get(p) and made[p] != n}
        since.update(made)
        save_record({"finished": True, "since": since, "skips": fingerprints, "last_point": name,
                     "last_finished": int(time.time()), "how": how, "thinned": thinned,
                     "away": away, "not_included": left_out,
                     "resent_for_pass": verdict.get("pass_started") if resend
                     else record.get("resent_for_pass")})
        for part_name, snap_name in old.items():
            opened[part_name].drop(snap_name)
    except BaseException:
        # Keep the old "since" snapshots; drop the new ones. If sending had
        # started, the record says "not finished": the next backup checks every file.
        for part_name, snap_name in made.items():
            if since.get(part_name) != snap_name:
                opened[part_name].drop(snap_name)
        raise
    finally:
        stack.close()
        try:
            gate.call("lock", bid, hold)
        except OmaError as exc:
            logger.warning("lock after backup: %s", exc.details)
    logger.info("backup %s done (%s): %s", name, "away" if away else "home", how)
    return {"point": name, "how": how, "away": away}


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
