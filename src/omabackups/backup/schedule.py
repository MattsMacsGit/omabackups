"""Is an automatic backup due? (D18; 1.x's way: the timer ticks every hour,
the backup itself decides from the settings.)"""

import os
import pwd
import time
from pathlib import Path

from omabackups.core import config, paths

INTERVAL = {"hourly": 3600, "daily": 86400, "weekly": 7 * 86400}


def user_settings(user: str) -> dict:
    """The linked user's settings, read as root from their own config folder."""
    try:
        home = Path(pwd.getpwnam(user).pw_dir)
    except KeyError:
        return config.defaults()
    if os.environ.get("OMABACKUPS_SYSROOT"):
        return config.load()   # tests: the sandbox's own settings
    return config.load(home / ".config" / "omabackups" / "settings.toml")


def due(settings: dict, last_finished: int | None, now: float | None = None) -> tuple[bool, str]:
    if not settings["automatic.on"]:
        return False, "automatic backups are off"
    if not last_finished:
        return True, "no backup has finished yet"
    interval = INTERVAL[settings["automatic.every"]]
    # The timer's random delay can leave two ticks a little under an hour apart.
    grace = interval / 12
    now = time.time() if now is None else now
    if now - last_finished >= interval - grace:
        return True, "due"
    return False, f"next one is due in about {int((interval - (now - last_finished)) / 60)} minutes"
