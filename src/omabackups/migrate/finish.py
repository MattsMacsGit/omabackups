"""The end of Migrate (D41): you land on your own desktop, ready to go.

When your files come back in the same run, Migrate waits for them first.
Then it restarts the computer: the keyring (your logins) and the services
only go live after a restart; a log-out isn't enough (testrig03, 9 Nov).
"Omarchy will now restart to apply your settings": Enter restarts now, and a
15 second countdown restarts anyway.
"""

import json
import select
import sys
import time

from omabackups.core import paths

COUNTDOWN = 15


def wait_for_files(say, poll: float = 2.0) -> dict:
    """Wait while Restore my files runs; its last state (done / error / stopped)."""
    state_file = paths.system_run_dir() / "restore.json"
    shown = -1
    while True:
        try:
            state = json.loads(state_file.read_text())
        except (OSError, ValueError):
            state = {}
        if state and not state.get("running"):
            return state
        percent = int(state.get("percent", 0) or 0)
        if percent != shown:
            say(f"Bringing back your files: {percent}%")
            shown = percent
        time.sleep(poll)


def _pressed_enter(timeout: float) -> bool:
    if not sys.stdin.isatty():
        time.sleep(timeout)
        return False
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if ready:
        sys.stdin.readline()
        return True
    return False


def restart(say, reboot, seconds: int = COUNTDOWN) -> None:
    """Say it, count down, restart. reboot(): restarts the computer."""
    say("")
    say("\033[1mOmarchy will now restart to apply your settings.\033[0m")
    say("\033[2mYour logins, services and desktop come back as they were.\033[0m")
    say("")
    for left in range(seconds, 0, -1):
        sys.stderr.write(f"\r  Press Enter to restart now, or it restarts in {left:2d} s ")
        sys.stderr.flush()
        if _pressed_enter(1.0):
            break
    sys.stderr.write("\n")
    say("Restarting...")
    reboot()
