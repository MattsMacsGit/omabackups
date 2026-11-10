"""The rescue on Omarchy's progress screen (D47), then the end screen.

restore/system.py does the work; this shows it: the traced logo through the
phases, one status line, a tip; then what was done, what to know (1.x's end
notes), "It's now safe to remove the USB", and the restart.
"""

import subprocess
import time

from omabackups.core.errors import OmaError
from omabackups.rescue import screens
from omabackups.rescue.progress import Progress
from omabackups.restore import system

TIPS = ("Your backup's password never leaves this stick.",
        "Nothing on your backup is changed by a rescue.",
        "Quick Rescue: your folders come back after it starts, with Restore my files.",
        "The restored computer starts just as it was at that restore point.")
END_NOTES = ("Unlocking with a fingerprint or TPM chip needs setting up again.",
             "Secure Boot must be off (or the boot file signed again) for it to start.",
             "It starts on UEFI computers (almost every computer from the last ten years).")


def _when(point: str) -> str:
    from omabackups.rescue.wizard import _when as when
    return when(point)


def run(events, gate, server, password, point, full, disk, disk_password, mine) -> int:
    phases = system.FULL_PHASES if full else system.PHASES
    progress = Progress(list(phases))
    tip = {"n": 0, "at": time.monotonic()}

    def show(phase: str, fraction: float, status: str) -> None:
        if time.monotonic() - tip["at"] > 12:
            tip.update(n=tip["n"] + 1, at=time.monotonic())
        progress.show(phase, fraction, status, TIPS[tip["n"] % len(TIPS)])

    try:
        done = system.rescue(gate, server["backup"], password, point, full, disk.path, disk_password, show)
    except OmaError as exc:
        progress.close()
        screens.step("The rescue stopped", exc.what)
        if exc.todo:
            screens.say(exc.todo, screens.GREY)
        if exc.details:
            screens.gap()
            screens.say("Details: " + exc.details[-600:], screens.GREY)
        screens.gap()
        screens.confirm("Start again?", "Start again", "Start again")
        events.result({"rescued": False, "error": exc.as_dict()}, exc.what)
        return 1
    progress.finish("Your computer is back", "")
    time.sleep(1.5)
    computer = mine.get("computer", "Your computer")
    screens.step("Your computer is back",
                 f"{computer}, as it was on {_when(point)}." +
                 ("" if full else " Your folders come back after it starts: Restore my files, on the panel."))
    for note in [*done.get("notes", []), *END_NOTES]:
        screens.say("· " + note, screens.GREY)
    screens.gap()
    screens.say("It's now safe to remove the USB.")
    screens.gap()
    events.result({"rescued": True, "point": point, "full": full}, "The rescue is done.")
    if screens.confirm("Restart now?", "Restart", "Stay here"):
        subprocess.run(["systemctl", "reboot"])
    return 0
