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
import threading
import time
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

from omabackups import __version__
from omabackups.audit import scan as audit_scan
from omabackups.backup import changes, check, health, reuse, schedule, skips, thinning
from omabackups.backup.send import Sender
from omabackups.backup.source import Snapshots, parts
from omabackups.core import ids, log, paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic
from omabackups.root import keys
from omabackups.where import location, network
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


def pause_automatic(why: str) -> None:
    """D29: automatic backups wait for a Back up now (fresh setup, Migrate,
    Rescue, the picker's choices changed). Root jobs call this."""
    save_record({**load_record(), "automatic_paused": True})
    log.get("backup").info("automatic backups wait for a Back up now (%s)", why)


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


def backup(progress=lambda step, part="": None, source=None, anyway: bool = False,
           manual: bool = True) -> dict:
    """Run one backup. `anyway`: the answer "Back up now" to the away limit.
    `source` (tests) stands in for this computer's parts and snapshots."""
    logger = log.get("backup")
    server = location.load()
    gate, away = location.connect(server)
    bid, line = server["backup"], server.get("line", "001")

    progress("unlock")
    gate_version = gate.check_version().get("gate", 0)
    if server.get("kind") != "disk":
        network.learn_addresses(gate, server)      # D48: at home or away, where it is now
    record = load_record()
    try:
        # Not before a migrated computer's takeover: it can only read until then.
        verdict = {} if server.get("migrating") else health.refresh(gate, bid)
    except OmaError as exc:
        logger.warning("health verdict: %s", exc.details)
        verdict = {}
    resend = health.resend_needed(verdict, record)    # damaged files go again, all of them
    hold = gate.call("unlock", bid, data=keys.read_unlock_key())["hold"]
    keeper = HoldKeeper(gate, bid, hold, logger)        # still here, however long a part takes
    if server.get("migrating"):
        line = handover(gate, server, logger)
    sender = Sender(gate, bid, line, compress=away)     # D25: zstd only when away
    run = datetime.now().strftime("%Y%m%dT%H%M%S")
    made, since, how, fingerprints, work, opened = {}, dict(record.get("since", {})), {}, {}, [], {}
    stack = ExitStack()
    try:
        # 1. Check first: snapshots and change lists for every part, and the size.
        progress("check")
        needed, known, left_out, manifests = 0, True, [], {}
        for part in (source.parts() if source else parts()):
            skip = skips.for_part(part.name)
            fingerprints[part.name] = skip.fingerprint()
            if not part.btrfs:
                work.append((part, skip, None, None))
                size, manifests[part.name] = check.folder_changes(
                    part.mount, record.get("manifests", {}).get(part.name, {}))
                needed += size
                continue
            snaps = stack.enter_context(source.snapshots(part) if source else Snapshots(part.device))
            opened[part.name] = snaps
            new = snaps.take(part, run)
            made[part.name] = new.name
            left_out += [f"{part.mount.rstrip('/')}/{rel}" for rel in snaps.nested(part)
                         if not skip.skipped(rel)]
            old = since.get(part.name, "")
            reusing = gate_version >= reuse.NEEDS_GATE
            if (not resend and record.get("finished") and snaps.exists(old)
                    and record.get("skips", {}).get(part.name) == fingerprints[part.name]):
                plan = changes.plan(snaps.dump(old, new), new.name, str(new), skip)
                needed += check.size_of(plan, str(new))
                if reusing:   # never send the same data twice (D25)
                    needed -= reuse.ask(gate, bid, line, part.name, [],
                                        reuse.fresh_files(plan, str(new)))["bytes"]
                work.append((part, skip, new, plan))
            else:
                known = False
                old_patterns = record.get("skip_patterns", {}).get(part.name)
                if reusing and old_patterns is not None and old_patterns != skip.patterns:
                    folders, files = reuse.unskipped(str(new), old_patterns, skip)
                    reuse.ask(gate, bid, line, part.name, folders, files)
                work.append((part, skip, new, None))
        settings = schedule.user_settings(linked_user())
        if settings["away.on"]:
            check.away_limit(away, anyway, needed if known else None, settings["away.limit_mb"])
        if known:
            check.make_room(gate, bid, needed, logger, may_delete=settings["thinning.on"])

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

        # 3. The restore point, then thinning.
        latest = changes_latest(gate, bid, line)
        name = point_name(line, latest)
        point = {"owner": ids.system_id(), "user": linked_user(), "omarchy": omarchy_version(),
                 "omabackups": __version__, "follows": latest, "how": how, "away": away,
                 "not_included": left_out,
                 "skips": {p: skips.for_part(p).patterns for p in how}, "created": int(time.time())}
        progress("audit")
        changes_now = audit_scan.safely(linked_user() or None)     # Your changes to Omarchy (D9)
        progress("point")
        files = {"point.json": point}
        if changes_now is not None and gate_version >= 9:
            files["changes.json"] = changes_now
        gate.call("snapshot", bid, line, name,
                  data=json.dumps(files if gate_version >= 9 else point).encode())
        if changes_now is not None:
            write_atomic(paths.system_state_dir() / "changes.json",
                         (json.dumps({**changes_now, "point": name}) + "\n").encode(), 0o644)
        thinned, left = thin(gate, bid, logger, smart=settings["thinning.on"])
        try:
            space = gate.call("space", bid)      # for the picker's bottom line
        except OmaError:
            space = {}

        # 4. Done: the new snapshots are the next "since" point; the old ones go.
        old = {p: n for p, n in since.items() if made.get(p) and made[p] != n}
        since.update(made)
        save_record({"finished": True, "since": since, "skips": fingerprints, "last_point": name,
                     "skip_patterns": {p: skips.for_part(p).patterns for p in fingerprints},
                     "point_skips": point_skips(record, name,
                                                {p: skips.for_part(p).patterns for p in fingerprints}, left),
                     "last_finished": int(time.time()), "how": how, "thinned": thinned,
                     "away": away, "not_included": left_out, "manifests": manifests,
                     "sent": sender.stats,
                     # D29: a manual backup ends the wait; an automatic one leaves it as it was.
                     "automatic_paused": False if manual else record.get("automatic_paused", False),
                     "kept": KEPT.get("kept", record.get("kept", [])),
                     "return_point": KEPT.get("return_point", record.get("return_point")),
                     "space": {k: space.get(k) for k in ("box", "used", "free")},
                     # Every restore point in the backup, every line: after a Migrate the
                     # old computer's (and the Return point) stay listed (stage 8 lesson).
                     "all_points": left if left is not None else record.get("all_points", []),
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
        keeper.stop()
        stack.close()
        try:
            gate.call("lock", bid, hold)
        except OmaError as exc:
            logger.warning("lock after backup: %s", exc.details)
    logger.info("backup %s done (%s): %s", name, "away" if away else "home", how)
    return {"point": name, "how": how, "away": away}


def handover(gate, server: dict, logger) -> str:
    """D22: a migrated computer's first backup takes the backup over. A new
    line starts from the restore point Migrate came from (only changes are
    stored); the old one is read-only now, and that point is the Return point.
    Recorded only once the server said yes."""
    point = server.get("from_point")
    if not point:
        raise OmaError("Migrate isn't finished on this computer yet.",
                       "Finish it first (the panel shows where it's up to).", code="migrate-unfinished")
    answer = gate.call("handover", server["backup"], point)
    # A new user name (testrig01 -> testrig02): the new line's copy of the home
    # folder takes this user's name, so only real changes are sent (stage 8:
    # 1.2 GB went again without this).
    old, new = server.get("from_user", ""), linked_user()
    if old and new and old != new:
        gate.call("apply", server["backup"], answer["line"], "home",
                  data=json.dumps([["rename", old, new]]).encode())
        logger.info("handover: the home folder %s is %s now", old, new)
    server = {**server, "line": answer["line"], "migrating": False,
              "return_point": answer["return_point"], "handed_over": int(time.time())}
    write_atomic(paths.server_file(), (json.dumps(server, indent=2) + "\n").encode(), 0o644)
    logger.info("handover: this computer owns the backup now, line %s from %s", answer["line"], point)
    return answer["line"]


class HoldKeeper:
    """Says "still here" to the server every 2 minutes for the whole backup. A
    hold nobody refreshes for 10 minutes counts as abandoned (1.x lesson: long
    jobs say so as they go); one slow part once outlasted it (stage 3 test)."""

    EVERY = 120

    def __init__(self, gate, bid: str, hold: str, logger):
        self.gate, self.bid, self.hold, self.logger = gate, bid, hold, logger
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while not self.done.wait(self.EVERY):
            try:
                self.gate.call("hold", self.bid, self.hold)
            except OmaError as exc:
                self.logger.warning("keeping the hold: %s", exc.details)

    def stop(self) -> None:
        self.done.set()
        self.thread.join(timeout=5)


KEPT = {}     # the kept restore points, as thinning last saw them


def thin(gate: Gate, bid: str, logger, smart: bool = True) -> tuple[list[str], list[str] | None]:
    """Smart thinning after each backup (D18); switched off (D35), every
    restore point stays until the backup needs the room. A problem here never
    fails the backup. Returns (the restore points removed, the ones left; None
    if unknown)."""
    gone, left = [], None
    try:
        info = gate.call("points", bid)
        kept = set(info["kept"].get("kept", [])) | {info["kept"].get("return_point")}
        for old in thinning.to_delete(info["points"], datetime.now(), kept) if smart else []:
            gate.call("delete", bid, old)
            gone.append(old)
        left = [n for n in info["points"] if n not in gone]
        KEPT.clear()
        KEPT.update(info["kept"])
    except OmaError as exc:
        logger.warning("thinning: %s | %s", exc.what, exc.details)
    return gone, left


def point_skips(record: dict, name: str, made: dict, left: list[str] | None) -> dict:
    """Each restore point with the skip list it was made with, for the picker's
    colours (what the backup holds); points thinning removed drop out."""
    out = dict(record.get("point_skips") or {})
    out[name] = {"time": int(time.time()), "skips": made}
    if left is not None:
        out = {n: v for n, v in out.items() if n in set(left) | {name}}
    return out


def changes_latest(gate: Gate, bid: str, line: str) -> str | None:
    names = [n for n in gate.call("points", bid)["points"] if n.startswith(f"{line}-")]
    return max(names) if names else None


def linked_user() -> str:
    try:
        return json.loads(paths.linked_user_file().read_text())["user"]
    except (OSError, ValueError, KeyError):
        return ""
