"""Browse (D37): open a restore point to look inside, read-only, as 1.x did.

Root jobs `browse-open` and `browse-close` start and stop a small service
(omabackups-browse, made with systemd-run) that holds the backup open and
mounts the restore point with sshfs, through the gatekeeper's read-only
`browse` verb. The user's side then opens it in their default file manager.
State: /run/omabackups/browse.json, written once it's really mounted.
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from omabackups.backup import run
from omabackups.core import log, paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic
from omabackups.root import keys
from omabackups.where import location

UNIT = "omabackups-browse"
POINT = run.thinning.NAME
READY_WAIT = 90      # seconds: unlocking a backup on a Pi can take a while


def state_file() -> Path:
    return paths.system_run_dir() / "browse.json"


def mount_dir(point: str) -> Path:
    return paths.system_run_dir() / "browse" / point


def current() -> dict:
    """What's open now ({} if nothing): point, path, ready, or error."""
    try:
        return json.loads(state_file().read_text())
    except (OSError, ValueError):
        return {}


def _check(point: str) -> str:
    point = str(point)
    if not POINT.match(point):
        raise OmaError("That isn't a restore point.", code="bad-request")
    return point


# --- the root jobs -------------------------------------------------------------

def open_job(request: dict) -> dict:
    point = _check(request.get("point", ""))
    user = run.linked_user()
    close_job({})                          # one at a time
    started = time.time()
    subprocess.run(["systemd-run", f"--unit={UNIT}", "--collect", "--quiet",
                    "--property=KillMode=mixed", sys.executable, "-m", "omabackups",
                    "browse-serve", point, user], check=False, capture_output=True)
    while time.time() - started < READY_WAIT:
        now = current()
        if now.get("point") == point and now.get("since", 0) >= int(started):
            if now.get("error"):
                raise OmaError(now["error"]["what"], now["error"].get("todo", ""),
                               now["error"].get("details", ""), code=now["error"].get("code", "browse"))
            if now.get("ready"):
                return now
        time.sleep(0.5)
    close_job({})
    raise OmaError("The restore point didn't open in time.",
                   "Try again. If your backup server is slow to answer, wait a minute first.",
                   f"{UNIT} not ready after {READY_WAIT} s", code="browse-slow")


def close_job(request: dict) -> dict:
    subprocess.run(["systemctl", "stop", f"{UNIT}.service"], check=False, capture_output=True)
    return {"closed": True}


# --- the service ------------------------------------------------------------------

def sshfs_options() -> str:
    """Read-only, mounted by root, readable by the user as far as each file's
    own owner and permissions allow (allow_other + default_permissions).
    1.x lesson: sshfs 3.7 refuses links pointing at ".." or a full path
    (contain_symlinks), so Files couldn't copy them; they're the user's own
    links and must come back as they were. Older sshfs doesn't know the option."""
    options = "passive,ro,allow_other,default_permissions,fsname=omabackups,subtype=omabackups"
    try:
        helps = subprocess.run(["sshfs", "-h"], capture_output=True, text=True).stdout
    except OSError:
        helps = ""
    return options + (",no_contain_symlinks" if "no_contain_symlinks" in helps else "")


def still_open(state: dict) -> dict | None:
    """The state, only if that restore point is really still mounted (1.x lesson:
    a session that ended without us must not leave the panel saying Browsing)."""
    if not state.get("ready") or not state.get("point"):
        return None
    return state if os.path.ismount(mount_dir(state["point"])) else None


def serve(point: str, user: str) -> int:
    """Runs in omabackups-browse until it's stopped (Done)."""
    point = _check(point)
    logger = log.get("browse")
    since = int(time.time())
    where = mount_dir(point)
    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    gate = bid = hold = keeper = pipe = fs = None
    try:
        server = location.load()
        gate, _away = location.connect(server)
        gate.check_version()
        bid = server["backup"]
        hold = gate.call("unlock", bid, data=keys.read_unlock_key())["hold"]
        keeper = run.HoldKeeper(gate, bid, hold, logger)
        where.mkdir(parents=True, exist_ok=True)
        argv, env = gate._argv(f"browse {bid} {point}")
        pipe = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
        fs = subprocess.Popen(["sshfs", "-f", "-o", sshfs_options(), "omabackups:/", str(where)],
                              stdin=pipe.stdout, stdout=pipe.stdin)
        for _ in range(60):
            if os.path.ismount(where) or fs.poll() is not None or stopping.is_set():
                break
            time.sleep(0.5)
        if not os.path.ismount(where):
            raise OmaError("The restore point couldn't be opened.",
                           "Try again. If it keeps failing, report it with the details.",
                           f"sshfs exit {fs.poll()}", code="browse-failed")
        home = where / "home" / user
        write_atomic(state_file(), json.dumps({
            "point": point, "since": since, "ready": True,
            "path": str(home if user and home.is_dir() else where)}).encode(), 0o644)
        logger.info("browsing %s", point)
        while not stopping.wait(1):
            if fs.poll() is not None:
                break
        return 0
    except OmaError as exc:
        write_atomic(state_file(), json.dumps({"point": point, "since": since,
                                               "error": exc.as_dict()}).encode(), 0o644)
        logger.error("browse %s: %s | %s", point, exc.what, exc.details)
        return 1
    finally:
        # 1.x lesson: the unmount often fails (sshfs got the stop signal
        # first); that must never stop the rest, above all the lock.
        if os.path.ismount(where):
            subprocess.run(["fusermount3", "-u", "-z", str(where)], capture_output=True)
        if os.path.ismount(where):
            subprocess.run(["umount", "-l", str(where)], capture_output=True)
        for proc in (fs, pipe):
            if proc and proc.poll() is None:
                proc.terminate()
        if keeper:
            keeper.stop()
        if gate and hold:
            try:
                gate.call("lock", bid, hold)
            except OmaError as exc:
                logger.warning("locking after browse: %s", exc.details)
        if current().get("ready") and current().get("point") == point:
            state_file().unlink(missing_ok=True)
        try:
            where.rmdir()
        except OSError:
            pass
