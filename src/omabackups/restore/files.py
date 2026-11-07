"""Restore my files (D37, as 1.x): bring the home folder back from a restore
point, never overwriting a file that's newer here (changed since).

Root jobs `restore-files-start` / `restore-files-stop` start and stop a
service (omabackups-restore, made with systemd-run). Stopped part-way, it
carries on later: whatever is already back is skipped.
State: /run/omabackups/restore.json (point, percent, running, done, error).
"""

import json
import pwd
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from omabackups.backup import run
from omabackups.core import log, paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic
from omabackups.root import keys
from omabackups.where import location

UNIT = "omabackups-restore"
PERCENT = re.compile(rb"\s(\d{1,3})%\s")


def state_file() -> Path:
    return paths.system_run_dir() / "restore.json"


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
    stop_job({})
    subprocess.run(["systemd-run", f"--unit={UNIT}", "--collect", "--quiet",
                    "--property=KillMode=mixed", sys.executable, "-m", "omabackups",
                    "restore-run", point, run.linked_user()], check=False, capture_output=True)
    return {"started": point}


def stop_job(request: dict) -> dict:
    subprocess.run(["systemctl", "stop", f"{UNIT}.service"], check=False, capture_output=True)
    return {"stopped": True}


def command(gate, bid: str, point: str, user: str, home: Path) -> list[str]:
    """rsync from the restore point's copy of this user's home into it.
    --update: a file that's newer here is never overwritten."""
    return ["rsync", "-aHAX", "--update", "--info=progress2", "--no-inc-recursive",
            "-e", gate.rsh(), f"--rsync-path=fetch {bid} {point} home",
            f"--filter=+ /{user}/", "--filter=- /*",
            f"{gate.rsync_target()}:home/", f"{home.parent}/"]


def restore(point: str, user: str, home: Path | None = None, stopping=lambda: False) -> dict:
    """Bring `user`'s home back from `point`. Returns the final state."""
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
        proc = subprocess.Popen(command(gate, bid, point, user, home), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=gate.rsync_env())
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
            state.update(running=False, done=True, percent=100)
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
        state = restore(point, user, stopping=lambda: stop["now"])
    except OmaError as exc:
        _say({"point": point, "user": user, "running": False, "error": exc.as_dict(),
              "since": int(time.time())})
        return 1
    return 0 if state.get("done") or state.get("stopped") else 1
