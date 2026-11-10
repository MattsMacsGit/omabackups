"""The rescue wizard (§7.3, D15, D47): what the Rescue USB starts into, full
screen on tty1, drawn like Omarchy's installer.

Wi-Fi (only without a working network) -> finding your backup (D48 order;
Tailscale offered when nothing answers) -> your backup's password ->
restore point -> Quick or Full Rescue -> the disk (every disk, what's on it;
the stick itself left out) -> the restored disk's password -> confirm ->
the restore (stage 9b) on Omarchy's progress screen.
"""

import subprocess
import time
from datetime import datetime

from omabackups.core.errors import OmaError
from omabackups.rescue import screens, settings, wifi

KINDS = ["Quick Rescue: your system and settings now, your files after it starts",
         "Full Rescue: everything in one go (start it and walk away)"]


def _when(point: str) -> str:
    from omabackups.backup.thinning import when
    d = when(point)
    return f"{d:%a %-d %b %Y, %-I:%M %p}" if isinstance(d, datetime) else point


def _problem(what: str, todo: str = "", details: str = "") -> None:
    screens.step(what, todo)
    if details:
        screens.say(details, screens.GREY)
        screens.gap()


def network() -> None:
    """A cable just works; otherwise the Wi-Fi, until it's connected."""
    while not wifi.online():
        dev = wifi.device()
        if not dev:
            _problem("No network found", "Plug in a network cable. The rescue carries on when it's connected.")
            for _ in range(30):
                if wifi.online():
                    return
                time.sleep(1)
            continue
        screens.step("No network cable found. Which Wi-Fi?", "Your Wi-Fi password is only used for this rescue.")
        screens.wait("Looking for Wi-Fi networks...", 0.1)
        found = wifi.networks(dev)
        names = [n["name"] for n in found] + ["Look again"]
        pick = screens.choose("Wi-Fi networks", names)
        if pick == len(found):
            continue
        net = found[pick]
        password = ""
        if net["security"] != "open":
            screens.step(f"Password for {net['name']}")
            password = screens.secret("Wi-Fi password", "the network's password")
        screens.step(f"Connecting to {net['name']}...")
        problem = wifi.connect(dev, net["name"], password)
        if problem:
            _problem(f"Couldn't connect to {net['name']}", "Check the password and try again.", problem)
            time.sleep(3)


def find_backup() -> tuple:
    """(server settings, the way in, away?): D48's order, Tailscale if needed."""
    from omabackups.where import location, network as net
    from omabackups.where.server import Gate
    server = location.load()
    while True:
        screens.step("Finding your backup")
        screens.wait("Looking for your backup server...", 0.1)
        try:
            address, away = net.route(server)
            screens.step("Found your backup server",
                         f"Through Tailscale ({address}): it's slower, but it works anywhere."
                         if away else f"On this network ({address}).")
            time.sleep(1.5)
            return server, Gate(address), away
        except OmaError as exc:
            _problem("Your backup server isn't answering on this network",
                     "If you're away from home, log in to Tailscale to reach it.", exc.details)
            if not screens.confirm("Log in to Tailscale?", "Log in", "Look again"):
                continue
            screens.step("Log in to Tailscale", "Open the link (or scan the code) on your phone and log in.")
            subprocess.run(["tailscale", "up", "--qr", "--accept-dns=true"])


def unlock(gate, bid: str) -> tuple[str, str]:
    """Your backup's password: tried on the server, asked again if wrong."""
    while True:
        screens.step("Your backup's password", "The one you chose when you set up backups.")
        password = screens.secret("Backup password", "your backup's password")
        try:
            hold = gate.call("unlock", bid, data=password.encode())["hold"]
            return password, hold
        except OmaError as exc:
            _problem("That password didn't open your backup", "Try again.", exc.what)
            time.sleep(2)


def pick_point(gate, bid: str, hold: str, mine: dict) -> str:
    listed = gate.call("points", bid)
    names = sorted(listed["points"], reverse=True)
    if not names:
        raise OmaError("Your backup has no restore points yet.", "Back up from the computer first.", code="no-points")
    kept = listed.get("kept") or {}
    computer, line = mine.get("computer", "this computer"), mine.get("line")

    def label(name: str) -> str:
        who = computer if line and name.startswith(f"{line}-") else f"an earlier computer (line {name[:3]})"
        notes = (["newest"] if name == names[0] else []) + \
                (["Return point"] if name == kept.get("return_point") else []) + \
                (["kept"] if name in kept.get("kept", []) else [])
        return f"{who}  ·  {_when(name)}" + (f"  ({', '.join(notes)})" if notes else "")
    screens.step("Which restore point?", "Each shows the computer it's from and when.")
    return names[screens.choose("Restore points", [label(n) for n in names])]


def pick_disk():
    from omabackups.rescue.disks import targets
    while True:
        found = targets()
        screens.step("Which disk should it go on?", "Every disk is listed with what's on it now.")
        if not found:
            _problem("No disk found to restore onto", "Connect the disk, then look again.")
            screens.confirm("Look again?", "Look again", "Look again")
            continue
        disk = found[screens.choose("Disks", [d.line() for d in found])]
        screens.clear_logo()
        screens.gap()
        for warning in disk.warnings:
            screens.say(warning, screens.RED if "erased" in warning or "internal" in warning else screens.GREY)
        screens.gap()
        if screens.confirm(f"Use {disk.path}?", "Use it", "Pick another"):
            return disk


def disk_password() -> str:
    while True:
        screens.step("A password for the restored disk",
                     "You type it every time the computer starts. Use the same one as before if you like.")
        first = screens.secret("Disk password", "at least 6 characters")
        again = screens.secret("Again", "the same password")
        if first != again:
            _problem("Those two didn't match", "Type it twice, the same both times.")
            time.sleep(2)
        elif len(first) < 6:
            _problem("That's too short", "Use at least 6 characters.")
            time.sleep(2)
        else:
            return first


def run(events) -> int:
    screens.step("OmaBackups Rescue", "Bring your computer back from your backup.")
    if not screens.confirm("Ready to start?", "Start", "Shut down"):
        subprocess.run(["systemctl", "poweroff"])
        return 0
    found = settings.find()
    if not found:
        raise OmaError("This stick has no settings.", "Make it again from your computer: Make Rescue USB.",
                       code="no-settings")
    mine = settings.install(found)
    network()
    server, gate, _away = find_backup()
    bid = server["backup"]
    password, hold = unlock(gate, bid)
    try:
        point = pick_point(gate, bid, hold, {**mine, "line": server.get("line")})
    finally:
        gate.call("lock", bid, hold)
    while True:          # "Change" comes back here: the backup stays found and opened once
        screens.step("Quick or Full Rescue?",
                     "Quick gets you working sooner. Full brings everything now and takes longer.")
        full = screens.choose("Rescue", KINDS) == 1
        disk = pick_disk()
        disk_pw = disk_password()
        screens.clear_logo()
        screens.gap()
        screens.say(f"Everything on {disk.line()} will be replaced", screens.RED)
        screens.say(f"by {mine.get('computer', 'your computer')} as it was on {_when(point)}.", screens.GREY)
        screens.gap()
        if screens.confirm("Start the rescue?", "Rescue", "Change"):
            break
    from omabackups.rescue import restore_run
    return restore_run.run(events, gate, server, password, point, full, disk, disk_pw, mine)
