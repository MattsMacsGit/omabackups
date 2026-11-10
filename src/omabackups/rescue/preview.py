"""`omabackups rescue-usb preview`: every Rescue USB screen in order, with
sample answers, so they can be seen and agreed before the stick is built
(D47). Nothing looks at the network or a disk; nothing changes.
"""

import time

from omabackups.rescue import screens
from omabackups.rescue.progress import Progress

NETWORKS = ["Home Wi-Fi", "Home Wi-Fi 5G", "Neighbour", "Guest"]
POINTS = ["laptop  ·  Tue 10 Nov 2026, 5:53 PM  (newest)",
          "laptop  ·  Mon 9 Nov 2026, 7:28 PM",
          "laptop  ·  Mon 9 Nov 2026, 3:41 PM  (Return point)",
          "old-laptop  ·  Sun 8 Nov 2026, 3:37 PM"]
KINDS = ["Quick Rescue: your system and settings now, your files after it starts",
         "Full Rescue: everything in one go (start it and walk away)"]
DISKS = ["Samsung 990 PRO 1 TB (nvme0n1)  ·  Omarchy, 412 GB used",
         "WD Blue 4 TB (sda)  ·  your files: Photos, Videos (3.1 TB used)",
         "SanDisk 64 GB (sdb)  ·  empty"]
TIPS = ["Your backup's password never leaves this stick.",
        "Quick Rescue brings your files back while you work: Restore my files on the panel.",
        "Nothing on the backup is changed by a rescue.",
        "The restored computer starts just as it was at that restore point."]


def _phases(full: bool) -> list[tuple[str, str, float]]:
    out = [("connect", "Connecting to your backup", 4), ("disk", "Preparing the disk", 4),
           ("system", "Bringing back your system", 45), ("settings", "Bringing back your settings", 10)]
    if full:
        out.append(("files", "Bringing back your files", 30))
    return out + [("start", "Making it start", 5)]


def run() -> int:
    screens.step("OmaBackups Rescue", "Bring your computer back from your backup.")
    if not screens.confirm("Ready to start?", "Start", "Shut down"):
        return 0

    screens.step("No network cable found. Which Wi-Fi?", "Your Wi-Fi password is only used for this rescue.")
    wifi = screens.choose("Wi-Fi networks", NETWORKS)
    screens.step(f"Password for {NETWORKS[wifi]}")
    screens.secret("Wi-Fi password", "the network's password")

    screens.step("Finding your backup")
    screens.wait("Looking for your backup server on this network...", 2)
    screens.step("Found your backup server", "On this network (sample: 192.0.2.34).")
    screens.wait("Checking it's really your server...", 1)

    screens.step("Your backup's password", "The one you chose when you set up backups.")
    screens.secret("Backup password", "your backup's password")

    screens.step("Which restore point?", "Each shows the computer it's from and when.")
    screens.choose("Restore points", POINTS)

    screens.step("Quick or Full Rescue?",
                 "Quick gets you working sooner. Full brings everything now and takes longer.")
    full = screens.choose("Rescue", KINDS) == 1

    screens.step("Which disk should it go on?", "Every disk is listed with what's on it now.")
    disk = screens.choose("Disks", DISKS)

    screens.clear_logo()
    screens.gap()
    screens.say(f"Everything on {DISKS[disk].split('  ·  ')[0]} will be replaced.", screens.RED)
    screens.say("by laptop as it was on Tue 10 Nov 2026, 5:53 PM.", screens.GREY)
    screens.gap()
    if not screens.confirm("Start the rescue?", "Rescue", "Change"):
        return run()

    phases = _phases(full)
    progress = Progress([(key, weight) for key, _, weight in phases])
    tip = 0
    for key, status, weight in phases:
        steps = max(4, int(weight))
        for n in range(steps + 1):
            progress.show(key, n / steps, status, TIPS[tip % len(TIPS)])
            time.sleep(0.12)
            if n % 12 == 11:
                tip += 1
    progress.finish("Your computer is back", "")
    time.sleep(1.5)

    screens.step("Your computer is back",
                 "laptop, as it was on Tue 10 Nov 2026, 5:53 PM." +
                 ("" if full else " Your files come back after it starts: Restore my files on the panel."))
    screens.say("It's now safe to remove the USB.", screens.GREY)
    screens.gap()
    screens.confirm("Restart now? (preview: nothing restarts)", "Restart", "Stay here")
    return 0
