"""Desktop notifications (SPEC §7; 1.x lib/common.sh notify_user): each kind
at most once a day, sent to the linked user's desktop from the root side.
The wording is as 1.x had it, agreed 14 Nov: don't reword it."""

import json
import os
import pwd
import subprocess
import time
from datetime import datetime
from pathlib import Path

from omabackups.core import log, paths
from omabackups.core.state import write_atomic

DAY = 86400
PAUSED = ("Automatic backups are paused",
          'This system was restored without your files. Open OmaBackups and press "Restore my files".')
FULL = ("Backup disk nearly full", "Less than 10% free. Delete old restore points or use a bigger disk.")
DAMAGE = ("Your backup's health check found damage",
          "Some files on your backup no longer match what was written. Open OmaBackups to see what to do.")
BATTERY = "The battery is under 20%."
UNREACHABLE = "Your backup can't be reached."
FAILED = "The last automatic backup failed."


def _stamps() -> Path:
    return paths.system_state_dir() / "notified.json"


def send(title: str, body: str, key: str) -> bool:
    """Shown at most once a day per key. Returns True when it was sent."""
    try:
        stamps = json.loads(_stamps().read_text())
    except (OSError, ValueError):
        stamps = {}
    if time.time() - float(stamps.get(key, 0)) < DAY:
        return False
    if os.environ.get("OMABACKUPS_SYSROOT"):       # tests: written down, never on this desktop
        paths.system_state_dir().mkdir(parents=True, exist_ok=True)
        with open(paths.system_state_dir() / "notifications.log", "a") as f:
            f.write(json.dumps([title, body]) + "\n")
    elif not _show(title, body):
        return False
    write_atomic(_stamps(), (json.dumps({**stamps, key: int(time.time())}) + "\n").encode(), 0o644)
    log.get("notify").info("notified: %s", title)
    return True


def _show(title: str, body: str) -> bool:
    command = ["notify-send", "-a", "OmaBackups", title, body]
    if os.geteuid() == 0:
        try:
            user = json.loads(paths.linked_user_file().read_text())["user"]
            uid = pwd.getpwnam(user).pw_uid
        except (OSError, ValueError, KeyError):
            return False
        bus = f"/run/user/{uid}/bus"
        if not os.path.exists(bus):
            return False                  # nobody logged in: nothing to show it on
        command = ["runuser", "-u", user, "--", "env", f"DBUS_SESSION_BUS_ADDRESS=unix:path={bus}", *command]
    try:
        return subprocess.run(command, capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def overdue(why: str, interval: int, last_finished: int | None, now: float | None = None) -> bool:
    """Three intervals without a finished backup (3 hours for hourly, 3 days
    for daily, 3 weeks for weekly): say so, with why."""
    now = time.time() if now is None else now
    if now - float(last_finished or 0) < 3 * interval:
        return False
    when = datetime.fromtimestamp(last_finished).strftime("%a %-d %b, %H:%M") if last_finished else "never"
    return send("No backup for a while", f"Last backup: {when}. {why}", "overdue")
