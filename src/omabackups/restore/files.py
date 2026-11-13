"""Restore my files (D37, as 1.x): bring the home folder back from a restore
point, never overwriting a file that's newer here (changed since).

Root jobs `restore-files-start` / `restore-files-stop` start and stop a
service (omabackups-restore, made with systemd-run). Stopped part-way, it
carries on later: whatever is already back is skipped.
State: /run/omabackups/restore.json (point, percent, running, done, error).
"""

import json
import os
import pwd
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from omabackups.backup import run
from omabackups.backup.skips import Skips
from omabackups.core import log, paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic
from omabackups.root import keys
from omabackups.where import location

UNIT = "omabackups-restore"
PERCENT = re.compile(rb"\s(\d{1,3})%\s")


USER = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")


def plan_file() -> Path:
    """What Migrate asked for (the old user name, just the picked folders)."""
    return paths.system_run_dir() / "restore-plan.json"


def state_file() -> Path:
    return paths.system_run_dir() / "restore.json"


def already_here(home: Path, folders: list[str]) -> list[str]:
    """Folders coming back that already have something in them here (a working
    clone in ~/src, say): old files would be added beside it (1.x test, 5 Nov)."""
    out = []
    for f in folders:
        p = home / f
        try:
            if p.is_dir() and not p.is_symlink() and any(p.iterdir()):
                out.append(f)
        except OSError:
            pass
    return out


def current() -> dict:
    try:
        return json.loads(state_file().read_text())
    except (OSError, ValueError):
        return {}


def _say(state: dict) -> None:
    write_atomic(state_file(), (json.dumps(state) + "\n").encode(), 0o644)


def start_job(request: dict) -> dict:
    point = str(request.get("point", ""))
    if not run.thinning.NAME.match(point):
        raise OmaError("That isn't a restore point.", code="bad-request")
    from_user = str(request.get("from_user") or "")
    if from_user and not USER.match(from_user):
        raise OmaError("That user name can't be used.", code="bad-request")
    only = request.get("only")
    if only is not None:
        only = [str(p).removeprefix("~/") for p in only if isinstance(p, str)]
        only = [p for p in only if p and ".." not in p.split("/") and not p.startswith("/")]
    leave_out = clean_leave_out(request.get("leave_out"))
    stop_job({})
    write_atomic(plan_file(), json.dumps({"point": point, "from_user": from_user, "only": only,
                                          "leave_out": leave_out}).encode(), 0o600)
    subprocess.run(["systemd-run", f"--unit={UNIT}", "--collect", "--quiet",
                    "--property=KillMode=mixed", sys.executable, "-m", "omabackups",
                    "restore-run", point, run.linked_user()], check=False, capture_output=True)
    return {"started": point}


def clean_leave_out(rules) -> list[str]:
    """D52: Choose what comes back's "leave in the backup" list, as skip rules
    relative to the home folder ("/Videos", ".cache", "!/Videos/keep")."""
    out = []
    for rule in rules if isinstance(rules, list) else []:
        body = str(rule).removeprefix("!")
        if isinstance(rule, str) and rule and len(rule) < 1000 and "\n" not in rule \
                and not body.startswith("-") and ".." not in body.split("/"):
            out.append(rule)
    return out


def stop_job(request: dict) -> dict:
    subprocess.run(["systemctl", "stop", f"{UNIT}.service"], check=False, capture_output=True)
    return {"stopped": True}


def command(gate, bid: str, point: str, user: str, home: Path, from_user: str = "",
            only: list[str] | None = None, leave_out: list[str] | None = None) -> list[str]:
    """rsync from the restore point's copy of a home folder into this user's.
    --update: a file that's newer here is never overwritten. `from_user`: the
    name it had there (1.x lesson: never assume it's the same on a new install);
    `only`: just these (relative paths), as Migrate's "Your files" picks them;
    `leave_out`: what Choose what comes back left in the backup (D52)."""
    owner = []
    if os.geteuid() == 0:                 # as root: the files become this user's
        entry = pwd.getpwnam(user)
        owner = [f"--chown={entry.pw_uid}:{entry.pw_gid}", "--numeric-ids"]
    return ["rsync", "-aHAX", "--update", "--info=progress2", "--no-inc-recursive", *owner,
            # --files-from switches off going into folders: -r puts it back
            # (stage 8 lesson: it made empty folders and said "done").
            *(["--files-from=-", "--from0", "-r"] if only is not None else []),
            *Skips(leave_out or []).rsync_rules(),
            "-e", gate.rsh(), f"--rsync-path=fetch {bid} {point} home/{from_user or user}",
            f"{gate.rsync_target()}:home/", f"{home}/"]


def still_missing(gate, bid: str, point: str, user: str, home: Path, from_user: str,
                  only: list[str] | None, leave_out: list[str] | None = None) -> int:
    """Check the result, not the exit code: rsync once more, as a dry run, and
    count the files it would still bring back (0 when everything's here)."""
    check = [a for a in command(gate, bid, point, user, home, from_user, only, leave_out)
             if not a.startswith("--info=")]
    check[1:1] = ["-n", "--out-format=%i %n"]
    done = subprocess.run(check, input=(b"\0".join(p.encode() for p in only) + b"\0") if only is not None else None,
                          capture_output=True, env=gate.rsync_env())
    return sum(1 for row in done.stdout.decode("utf-8", "replace").splitlines() if row.startswith(">f"))


def restore(point: str, user: str, home: Path | None = None, stopping=lambda: False,
            from_user: str = "", only: list[str] | None = None, leave_out: list[str] | None = None) -> dict:
    """Bring `user`'s home back from `point` (from `from_user`'s folder there,
    or just the paths in `only`). Returns the final state."""
    logger = log.get("restore")
    home = home or Path(pwd.getpwnam(user).pw_dir)
    state = {"point": point, "user": user, "percent": 0, "running": True, "since": int(time.time())}
    _say(state)
    server = location.load()
    gate, _away = location.connect(server)
    gate.check_version()
    bid = server["backup"]
    hold = gate.call("unlock", bid, data=keys.read_unlock_key())["hold"]
    keeper = run.HoldKeeper(gate, bid, hold, logger)
    try:
        proc = subprocess.Popen(command(gate, bid, point, user, home, from_user, only, leave_out),
                                stdin=subprocess.PIPE if only is not None else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=gate.rsync_env())
        if only is not None:
            proc.stdin.write(b"\0".join(p.encode() for p in only) + b"\0")
            proc.stdin.close()
        buffer = b""
        while chunk := proc.stdout.read1(4096):
            buffer = (buffer + chunk)[-400:]
            found = PERCENT.findall(buffer)
            if found and int(found[-1]) != state["percent"]:
                state["percent"] = min(100, int(found[-1]))
                _say(state)
            if stopping():
                proc.terminate()
        error = proc.stderr.read().decode("utf-8", "replace")
        code = proc.wait()
        if stopping():
            state.update(running=False, stopped=True)
        elif code not in (0, 24):          # 24: some files vanished (fine)
            failure = OmaError("Your files couldn't all be brought back.",
                               "Run Restore my files again: it carries on where it stopped.",
                               error.strip()[-2000:] or f"rsync exit {code}", code="restore-failed")
            state.update(running=False, error=failure.as_dict())
        else:
            missing = still_missing(gate, bid, point, user, home, from_user, only, leave_out)
            if missing:
                failure = OmaError(f"{missing} of your files didn't come back.",
                                   "Run Restore my files again: it brings back what's still missing.",
                                   f"a check after the copy found {missing} files still to bring back",
                                   code="restore-incomplete")
                state.update(running=False, error=failure.as_dict())
            else:
                state.update(running=False, done=True, percent=100)
                from omabackups.core import partial      # the guard counts what's back (SPEC §9)
                partial.note_restored(point, only, leave_out)
                from omabackups.migrate import rename      # sync apps' folders (Migrate, 8b)
                if again := rename.later(user):
                    state["note"] = (f"{' and '.join(again)} now uses your folders here: "
                                     "start it again from the app menu.")
        _say(state)
        logger.info("restore my files from %s: %s", point,
                    "done" if state.get("done") else "stopped" if state.get("stopped") else "failed")
        return state
    finally:
        keeper.stop()
        try:
            gate.call("lock", bid, hold)
        except OmaError as exc:
            logger.warning("locking after restore: %s", exc.details)


def serve(point: str, user: str) -> int:
    """Runs in omabackups-restore."""
    stop = {"now": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(now=True))
    try:
        asked = json.loads(plan_file().read_text())
    except (OSError, ValueError):
        asked = {}
    if asked.get("point") != point:
        asked = {}
    try:
        state = restore(point, user, stopping=lambda: stop["now"],
                        from_user=asked.get("from_user") or "", only=asked.get("only"),
                        leave_out=clean_leave_out(asked.get("leave_out")))
    except OmaError as exc:
        _say({"point": point, "user": user, "running": False, "error": exc.as_dict(),
              "since": int(time.time())})
        return 1
    return 0 if state.get("done") or state.get("stopped") else 1
