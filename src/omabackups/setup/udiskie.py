"""Stops udiskie (Omarchy's USB auto-mounter) opening OmaBackups' own disks
and the Rescue USB the moment they're plugged in (1.x lib/udiskie-rule.sh;
audit 7.4).

The udev rule (packaging/files/99-omabackups.rules) marks only our partitions
"don't open this on its own" (UDISKS_AUTO=0); the file manager honours that,
udiskie doesn't. This adds a marked block to udiskie's settings so it does.
An ordinary USB stick isn't marked and mounts exactly as before. The user's
own udiskie settings are never overwritten: where the block can't be added
safely, it says what to add.
"""

import os
import shutil
import subprocess
from pathlib import Path

BEGIN, END = "# >>> OmaBackups", "# <<< OmaBackups"
BLOCK = f"""{BEGIN}
# Don't open or ask to unlock a disk the system marks "not on its own"
# (UDISKS_AUTO=0). OmaBackups marks only its own disks and its Rescue USB.
device_config:
  - should_automount: false
    automount: false
{END}
"""
OWN_SETTINGS = ("You have your own udiskie settings, so they were left alone. To stop it opening "
                "OmaBackups' disks when they're plugged in, add to device_config in {conf}:\n"
                "  - should_automount: false\n    automount: false")


def folder() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "udiskie"


def install() -> str:
    """Adds the block once. Returns a note for the user, or ""."""
    conf = folder() / "config.yml"
    text = conf.read_text() if conf.is_file() else ""
    if BEGIN in text.splitlines():
        return ""
    if (folder() / "config.json").exists() or any(line.startswith("device_config:") for line in text.splitlines()):
        return OWN_SETTINGS.format(conf=conf)
    conf.parent.mkdir(parents=True, exist_ok=True)
    conf.write_text((text.rstrip("\n") + "\n\n" if text.strip() else "") + BLOCK)
    restart()
    return ""


def remove() -> None:
    conf = folder() / "config.yml"
    if not conf.is_file():
        return
    lines, out, inside = conf.read_text().splitlines(), [], False
    if BEGIN not in lines:
        return
    for line in lines:
        if line == BEGIN:
            inside = True
        elif line == END:
            inside = False
        elif not inside:
            out.append(line)
    if any(line.strip() for line in out):
        conf.write_text("\n".join(out).rstrip("\n") + "\n")
    else:                              # nothing of the user's was in it: it was ours alone
        conf.unlink()
        try:
            conf.parent.rmdir()
        except OSError:
            pass
    restart()


def restart() -> None:
    """udiskie reads its settings once, at start: relaunch it the way it was
    started (detached; uwsm-app is how Omarchy starts it)."""
    if os.environ.get("OMABACKUPS_SYSROOT"):
        return                              # tests: never this computer's udiskie
    found = subprocess.run(["pgrep", "-x", "-u", str(os.getuid()), "udiskie"], capture_output=True, text=True)
    pid = found.stdout.split()[0] if found.stdout.split() else ""
    try:
        args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")[:-1] if pid else []
    except OSError:
        return
    args = [a.decode() for a in args]
    if args and os.path.basename(args[0]).startswith("python"):
        args = args[1:]                     # a Python script's command line starts with the interpreter
    if not args:
        return
    subprocess.run(["kill", pid], capture_output=True)
    launcher = ["uwsm-app", "--"] if shutil.which("uwsm-app") else []
    subprocess.Popen(["setsid", "-f", *launcher, *args], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
