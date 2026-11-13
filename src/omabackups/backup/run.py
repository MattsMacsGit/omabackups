"""One backup, start to end (as root; BUILD 6.1 D, D25), as its steps:

0. guard   not while this system waits for its folders (a Quick Rescue or a
           Migrate, SPEC §9), unless forced; a forced one keeps that point.
1. open    unlock your backup on the server (a hold); the health verdict.
2. check   for each part: a fresh read-only snapshot, then the everyday mix
           if the last backup finished and the skip list hasn't changed,
           else a full check. The size, and the away limit.
3. clear   every part's deletes first, then the room is checked.
4. send    each part.
5. point   the restore point on the server (point.json inside it).
6. tidy    thinning; only then the new snapshots become the "since" point
           and the old ones go.
Resume: the record says "not finished" from the first change on the server;
a run that's cut off (network, power, crash) leaves it so, and the next run
checks every file: rsync only sends what's still missing.
"""

import json
import subprocess
import time
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

from omabackups import __version__
from omabackups.audit import scan as audit_scan
from omabackups.backup import (
    after,
    changes,
    check,
    full,
    health,
    reuse,
    schedule,
    skips,
    thinning,  # noqa: F401  (run.thinning: other modules use it)
    todo,
)
from omabackups.backup.handover import handover
from omabackups.backup.hold import HoldKeeper
from omabackups.backup.job import Job
from omabackups.backup.send import Sender
from omabackups.backup.source import Snapshots, parts
from omabackups.core import ids, log, partial, paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic
from omabackups.root import keys
from omabackups.where import location, network

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


def pause_automatic(why: str) -> None:
    """D29: automatic backups wait for a Back up now (fresh setup, Migrate,
    Rescue, the picker's choices changed). Root jobs call this."""
    save_record({**load_record(), "automatic_paused": True})
    log.get("backup").info("automatic backups wait for a Back up now (%s)", why)


def linked_user() -> str:
    try:
        return json.loads(paths.linked_user_file().read_text())["user"]
    except (OSError, ValueError, KeyError):
        return ""


def renamed_home(server: dict, part: str) -> tuple[str, str] | None:
    """(this user, the name it had) when Migrate came from another user name:
    reuse looks for files under the old name too (stage 10)."""
    old = server.get("from_user", "")
    if part != "home" or not old:
        return None
    try:
        new = linked_user()
    except Exception:  # noqa: BLE001  (no linked user: nothing to map)
        return None
    return (new, old) if new and new != old else None


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


def backup(progress=lambda step, part="", **more: None, source=None, anyway: bool = False,
           manual: bool = True, force_after_restore: bool = False) -> dict:
    """Run one backup. `anyway`: the answer "Back up now" to the away limit.
    `force_after_restore`: Back up anyway, while the folders of a partial
    restore are still on the backup (SPEC §9).
    `source` (tests) stands in for this computer's parts and snapshots."""
    left = partial.waiting()
    if left and not force_after_restore:
        raise partial.refusal(left)
    job = open_backup(progress)
    if left:
        job.forced_past = left["point"]
        job.logger.warning("backing up anyway after a partial restore from %s (still on the backup: %s)",
                           left["point"], ", ".join(left["folders"]))
    keeper = HoldKeeper(job.gate, job.bid, job.hold, job.logger)  # still here, however long a part takes
    stack = ExitStack()
    try:
        take_over(job)
        check_parts(job, source, stack)
        job.settings = schedule.user_settings(linked_user())
        if job.settings["away.on"]:
            check.away_limit(job.away, anyway, job.needed if job.known else None,
                             job.settings["away.limit_mb"])
        clear(job)
        room(job)
        send(job)
        name = make_point(job)
        after.keep_forced_point(job)
        tidy(job, name, manual)
    except BaseException:
        drop_new(job)
        raise
    finally:
        keeper.stop()
        stack.close()
        try:
            job.gate.call("lock", job.bid, job.hold)
        except OmaError as exc:
            job.logger.warning("lock after backup: %s", exc.details)
    job.logger.info("backup %s done (%s): %s", name, "away" if job.away else "home", job.how)
    return {"point": name, "how": job.how, "away": job.away}


# --- 1. open ------------------------------------------------------------------

def open_backup(progress) -> Job:
    """Connect, unlock (a hold), and the health verdict."""
    logger = log.get("backup")
    server = location.load()
    gate, away = location.connect(server)
    progress("unlock")
    gate_version = gate.check_version().get("gate", 0)
    if server.get("kind") != "disk":
        network.learn_addresses(gate, server)      # D48: at home or away, where it is now
    record = load_record()
    job = Job(gate=gate, server=server, away=away, gate_version=gate_version, record=record,
              progress=progress, logger=logger, since=dict(record.get("since", {})))
    try:
        # Not before a migrated computer's takeover: it can only read until then.
        job.verdict = {} if server.get("migrating") else health.refresh(gate, job.bid)
    except OmaError as exc:
        logger.warning("health verdict: %s", exc.details)
    job.resend = health.resend_needed(job.verdict, record)
    job.hold = gate.call("unlock", job.bid, data=keys.read_unlock_key())["hold"]
    return job


def take_over(job: Job) -> None:
    """A migrated computer takes the backup over (D22); then the sender."""
    if job.server.get("migrating"):
        job.server = {**job.server, "line": handover(job.gate, job.server, linked_user(), job.logger)}
    # D49: stuck for 3 minutes. The first full backup stays manual (D29).
    first = not job.record.get("last_point") or job.record.get("automatic_paused")
    job.sender = Sender(job.gate, job.bid, job.line, compress=job.away,     # D25: zstd only when away
                        stuck_todo="Press Resume backup when you're connected again: it carries on "
                                   "from where it got to." if first else
                                   "It tries again at the next automatic backup, from where it got to.")


# --- 2. check -----------------------------------------------------------------

def check_parts(job: Job, source, stack: ExitStack) -> None:
    """Check first: snapshots and change lists for every part, and the size."""
    job.progress("check")
    for part in (source.parts() if source else parts()):
        job.progress("check", part.name)
        job.sender.report = lambda fields, name=part.name: job.progress("check", name, **fields)
        skip = skips.for_part(part.name)
        job.fingerprints[part.name] = skip.fingerprint()
        if not part.btrfs:
            job.work.append((part, skip, None, None))
            size, job.manifests[part.name] = check.folder_changes(
                part.mount, job.record.get("manifests", {}).get(part.name, {}))
            job.needed += size
            continue
        snaps = stack.enter_context(source.snapshots(part) if source else Snapshots(part.device))
        job.opened[part.name] = snaps
        new = fresh_snapshot(job, part, skip, snaps)
        plan = (everyday_plan(job, part, skip, snaps, new) if everyday(job, part.name, snaps)
                else full_plan(job, part, skip, snaps, new))
        job.work.append((part, skip, new, plan))


def fresh_snapshot(job: Job, part, skip, snaps):
    # A stopped backup is killed, so it never tidies up: its snapshot stayed
    # for good. Only the "since" one and an unfinished full backup's are
    # needed (D49); this run's comes next.
    still_used = {job.since.get(part.name), full.keep(part.name)}
    for name in snaps.names():
        if name.startswith(f"{part.name}-") and name not in still_used:
            snaps.drop(name)
    new = snaps.take(part, job.run)
    job.made[part.name] = new.name
    job.left_out += [f"{part.mount.rstrip('/')}/{rel}" for rel in snaps.nested(part)
                     if not skip.skipped(rel)]
    return new


def everyday(job: Job, name: str, snaps) -> bool:
    """The everyday mix: the last backup finished, its snapshot is still
    here, the skip list is the same, and nothing has to be sent again."""
    return bool(not job.resend and job.record.get("finished") and snaps.exists(job.since.get(name, ""))
                and job.record.get("skips", {}).get(name) == job.fingerprints[name])


def everyday_plan(job: Job, part, skip, snaps, new):
    plan = changes.plan(snaps.dump(job.since.get(part.name, ""), new), new.name, str(new), skip)
    job.needed += check.size_of(plan, str(new))
    if job.reusing:   # never send the same data twice (D25)
        job.needed -= reuse.ask(job.gate, job.bid, job.line, part.name, [],
                                reuse.fresh_files(plan, str(new), renamed_home(job.server, part.name)))["bytes"]
    return plan


def full_plan(job: Job, part, skip, snaps, new):
    """A full check: once, as a to-do list (D49 C), when the server can;
    None means rsync checks every file as it goes and the size isn't known."""
    old_patterns = job.record.get("skip_patterns", {}).get(part.name)
    if job.reusing and old_patterns is not None and old_patterns != skip.patterns:
        folders, files = reuse.unskipped(str(new), old_patterns, skip)
        reuse.ask(job.gate, job.bid, job.line, part.name, folders, files)
    if job.resend or job.gate_version < full.NEEDS_GATE:
        job.known = False
        return None
    listed = full.prepare(part.name, skip, new, snaps, job.sender, job.record, job.bid, job.line,
                          job.fingerprints[part.name], job.logger)
    if listed.old_snapshot and listed.old_snapshot not in (new.name, job.since.get(part.name)):
        snaps.drop(listed.old_snapshot)
    job.needed += sum(size for _, size in listed.items)      # D50: known, so checked
    return listed


# --- 3. clear, and the room ---------------------------------------------------

def not_finished(job: Job) -> None:
    """From the first change on the server until the end, the record says so."""
    save_record({**job.record, "finished": False, "started": int(time.time())})


def clear(job: Job) -> None:
    """Every part's deletes first: the room they free is there before the
    room is checked and before anything is copied (a full space failed on
    7 MB of system files while home's skipped folders waited)."""
    for part, _skip, _new, plan in job.work:
        if isinstance(plan, full.FullList) and plan.ops:
            not_finished(job)
            job.progress("clear", part.name)
            job.sender.remove(part.name, plan.ops)
            plan.ops = []


def room(job: Job) -> None:
    if job.known:     # D50: won't fit -> said before anything is sent
        check.make_room(job.gate, job.bid, job.needed, job.logger, may_delete=job.settings["thinning.on"])


# --- 4. send ------------------------------------------------------------------

def send(job: Job) -> None:
    not_finished(job)
    for number, (part, skip, new, plan) in enumerate(job.work, 1):
        job.progress("send", part.name, part_no=number, parts=len(job.work))
        job.sender.report = lambda fields, name=part.name, n=number: job.progress(
            "send", name, part_no=n, parts=len(job.work), **fields)
        job.how[part.name] = send_part(job, part, skip, new, plan)


def send_part(job: Job, part, skip, new, plan) -> str:
    """Send one part; says how it went."""
    sender = job.sender
    if new is None:
        sender.full(part.name, part.mount, skip)
        return "copied"
    if isinstance(plan, full.FullList):
        sender.copy(part.name, str(new), plan.items, plan.already)
        return "full, carried on" if plan.resumed else "full, checked once"
    if plan is not None:
        sender.everyday(part.name, str(new), plan, check.size_of(plan, str(new)))
        return f"changes ({len(plan.files)} files, {len(plan.ops)} moves/deletes)"
    sender.full(part.name, str(new), skip, checksum=job.resend)
    return "full check, every file's contents" if job.resend else "full check"


# --- 5. the restore point -----------------------------------------------------

def make_point(job: Job) -> str:
    latest = after.changes_latest(job.gate, job.bid, job.line)
    name = point_name(job.line, latest)
    point = {"owner": ids.system_id(), "user": linked_user(), "omarchy": omarchy_version(),
             "omabackups": __version__, "follows": latest, "how": job.how, "away": job.away,
             "not_included": job.left_out,
             "skips": {p: skips.for_part(p).patterns for p in job.how}, "created": int(time.time())}
    job.progress("audit")
    changes_now = audit_scan.safely(linked_user() or None)     # Your changes to Omarchy (D9)
    job.progress("point")
    files = {"point.json": point}
    if changes_now is not None and job.gate_version >= 9:
        files["changes.json"] = changes_now
    job.gate.call("snapshot", job.bid, job.line, name,
                  data=json.dumps(files if job.gate_version >= 9 else point).encode())
    if changes_now is not None:
        write_atomic(paths.system_state_dir() / "changes.json",
                     (json.dumps({**changes_now, "point": name}) + "\n").encode(), 0o644)
    return name


# --- 6. tidy ------------------------------------------------------------------

def tidy(job: Job, name: str, manual: bool) -> None:
    """Thinning; then the new snapshots are the next "since" point; the old ones go."""
    thinned, left = after.thin(job.gate, job.bid, job.logger, smart=job.settings["thinning.on"])
    try:
        space = job.gate.call("space", job.bid)      # for the picker's bottom line
    except OmaError:
        space = {}
    old = {p: n for p, n in job.since.items() if job.made.get(p) and job.made[p] != n}
    job.since.update(job.made)
    save_record(after.finished_record(job, name, thinned, left, space, manual))
    for part_name, snap_name in old.items():
        job.opened[part_name].drop(snap_name)
    for part_name in job.made:
        todo.clear(part_name)          # finished: everyday backups carry on (D49)


def drop_new(job: Job) -> None:
    """A backup that didn't finish keeps the old "since" snapshots and drops
    the new ones. If sending had started, the record says "not finished": the
    next backup checks every file. A full backup's to-do list keeps its
    snapshot: the next run carries on (D49)."""
    for part_name, snap_name in job.made.items():
        if job.since.get(part_name) != snap_name and full.keep(part_name) != snap_name:
            job.opened[part_name].drop(snap_name)
