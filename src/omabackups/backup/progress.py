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

STEPS = {"unlock": "Opening your backup", "send": "Backing up", "point": "Making the restore point"}


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
