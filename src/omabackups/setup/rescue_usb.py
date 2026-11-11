"""Make / Refresh Rescue USB (9c, D11, D16), in a terminal window the panel
opens, drawn like setup (Omarchy installer style, D31).

Make: which stick (every disk, with what's on it; the one this system runs
on left out) -> the rescue system downloaded (size first, resumes, checked,
kept) -> written to the stick with its small settings part and its own
read-only key (the last stick's cut off) -> done.
Refresh: only the stick's settings part (seconds); a newer rescue system is
offered, with its size.
"""

import json
import threading
import time

from omabackups.backup.check import human
from omabackups.core import paths, rootjob, state
from omabackups.core.errors import OmaError
from omabackups.setup import disks, menu
from omabackups.setup import rescue_image as image


def _pick_stick(purpose: str):
    found = disks.disks()
    if not found:
        raise OmaError("No USB stick or other disk found.", "Plug in a USB stick (4 GB or more), then try again.",
                       code="no-disk")
    menu.title(f"Which stick {purpose}?", "Every disk is listed with what's on it now. Pick the USB stick.")
    disk = found[menu.choose("Disks", [d.line() for d in found])]
    menu.title(f"{disk.line()}")
    for warning in disk.warnings:
        menu.say(f"  {warning}")
    menu.say()
    if menu.choose("Use this one?", ["Yes, use it", "No, stop here"], 1) != 0:
        raise OmaError(menu.CANCELLED, code="cancelled")
    return disk


def _the_image() -> str:
    menu.title("The rescue system", "Checking what's published...")
    want = image.published()
    if image.have(want):
        menu.say(f"  Already downloaded ({human(image.path().stat().st_size)}), checked.")
        return str(image.path())
    size = human(want["size"]) if want["size"] else "about 1.5 GB"
    menu.title(f"The rescue system is {size}",
               "It's downloaded once and kept. If the download stops, it carries on where it stopped.")
    if menu.choose("Download it now?", ["Download", "Not now"]) != 0:
        raise OmaError(menu.CANCELLED, code="cancelled")
    image.download(want)
    menu.say("  Downloaded and checked.")
    return str(image.path())


def _with_progress(job: str, request: dict, what: str) -> dict:
    """A root job, with its progress on screen as it goes."""
    result, failure = {}, []

    def work():
        try:
            result.update(rootjob.run(job, request))
        except OmaError as exc:
            failure.append(exc)
    worker = threading.Thread(target=work)
    worker.start()
    shown = ""
    while worker.is_alive():
        try:
            now = json.loads((paths.system_run_dir() / "rescue-usb.json").read_text())
        except (OSError, ValueError):
            now = {}
        line = {"write": f"Writing the rescue system: {now.get('percent', 0)}%",
                "settings": "Adding the stick's settings and its own key...",
                "done": "Finishing..."}.get(now.get("step"), what)
        if line != shown:
            menu.say(f"  {line}")
            shown = line
        time.sleep(1)
    worker.join()
    if failure:
        raise failure[0]
    return result


def _remember(made: dict, disk) -> None:
    mine = state.read("panel") or {}
    state.write("panel", {**mine, "rescue_later": False,
                          "rescue_usb": {"made": made.get("made", int(time.time())), "stick": disk.line(),
                                         "key": made.get("key", "")}})


def make() -> dict:
    disk = _pick_stick("should become the Rescue USB")
    path = _the_image()
    menu.title(f"Everything on {disk.path} will be erased",
               "It becomes your Rescue USB. Your computer's password is asked for (a pop-up).")
    if menu.choose("Make the Rescue USB?", ["Make it", "No, stop here"], 1) != 0:
        raise OmaError(menu.CANCELLED, code="cancelled")
    done = _with_progress("rescue-usb-write", {"disk": disk.path, "image": path}, "Starting...")
    _remember(done.get("made", {}), disk)
    menu.title("Your Rescue USB is ready",
               "Keep it somewhere safe. To bring this computer back, start it from the stick.\n"
               "Every rescue asks for your backup's password: the stick can't open your backup by itself.")
    return done


def refresh() -> dict:
    want = None
    try:
        want = image.published()
    except OmaError:
        pass        # offline: only the settings part, which needs no download
    if want and not image.have(want) and image.path().is_file():
        menu.title(f"A newer rescue system is ready ({human(want['size'])})",
                   "Make the stick again with it, or only refresh its settings.")
        if menu.choose("What now?", ["Make it again with the newer one", "Only the settings"]) == 0:
            return make()
    disk = _pick_stick("is your Rescue USB")
    done = _with_progress("rescue-usb-refresh", {"disk": disk.path}, "Refreshing its settings...")
    _remember(done.get("made", {}), disk)
    menu.title("Your Rescue USB is up to date", "The last stick's key no longer opens anything.")
    return done
