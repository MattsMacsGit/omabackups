"""The running backup's progress, for the panel and `omabackups backup`
(BUILD 5.2: root jobs report through a file the user can read).

/run/omabackups/progress.json:
  {"running": true, "kind": "now"|"scheduled", "step": "...", "part": "...", "started": ...}
  {"running": false, "ok": true, "point": "...", ...}  or  {"running": false, "ok": false, "error": {...}}
"""

import fcntl
import json
import os
import time
from contextlib import contextmanager

from omabackups.core import paths
from omabackups.core.state import write_atomic

STEPS = {"unlock": "Opening your backup", "check": "Checking what changed",
         "send": "Backing up", "audit": "Noting your changes to Omarchy",
         "point": "Making the restore point"}


def file():
    return paths.system_run_dir() / "progress.json"


def write(data: dict) -> None:
    paths.system_run_dir().mkdir(parents=True, exist_ok=True)
    write_atomic(file(), (json.dumps(data) + "\n").encode(), 0o644)


def read() -> dict:
    try:
        return json.loads(file().read_text())
    except (OSError, ValueError):
        return {}


def alive(data: dict) -> bool:
    """A backup the progress file says is running really is: its service is
    still up. Stopped or killed, nobody tidies the file, and the panel showed
    "running" for ever."""
    kind = data.get("kind")
    if not data.get("running") or not kind:
        return bool(data.get("running"))
    import subprocess
    done = subprocess.run(["systemctl", "--no-ask-password", "is-active", f"omabackups-backup@{kind}.service"],
                          capture_output=True, text=True)
    # 0: active; starting and stopping answer non-zero but say so.
    return done.returncode == 0 or done.stdout.strip() in ("activating", "reloading", "deactivating")


def text(data: dict) -> str:
    step = STEPS.get(data.get("step", ""), data.get("step", ""))
    part = data.get("part", "")
    return f"{step} {part}".strip() + "..."


@contextmanager
def only_one():
    """One backup at a time. Yields False if another one is already running."""
    paths.system_run_dir().mkdir(parents=True, exist_ok=True)
    fd = os.open(paths.system_run_dir() / "backup.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        os.close(fd)


def reporter(kind: str):
    started = int(time.time())

    def report(step: str, part: str = "") -> None:
        write({"running": True, "kind": kind, "step": step, "part": part, "started": started})
    return report
