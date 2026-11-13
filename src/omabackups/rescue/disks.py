"""The disks a rescue can go onto: every disk, each with what's on it (the
rule: warn, never block, never hide one), except the stick the rescue is
running from and anything the running system is on.

The stick is found three ways, because the first can vanish: where archiso
mounted it (/run/archiso/bootmnt), the stick's ID on the boot line
(archisosearchuuid=, there even when the rescue system was copied into
memory and the stick unmounted: then the stick was offered as a target),
and its settings part, mounted by the wizard.
"""

import subprocess
from pathlib import Path

from omabackups.rescue.settings import PLACES
from omabackups.setup import disks as setup_disks

BOOT = "/run/archiso/bootmnt"
CMDLINE = Path("/proc/cmdline")


def _source(where: str) -> str:
    return subprocess.run(["findmnt", "-n", "-o", "SOURCE", where], capture_output=True,
                          text=True).stdout.strip()


def _boot_ids() -> list[str]:
    try:
        words = CMDLINE.read_text().split()
    except OSError:
        return []
    out = []
    for word in words:
        key, _, value = word.partition("=")
        if key == "archisosearchuuid" and value:
            out.append(value)
        elif key == "archisodevice" and value.startswith("UUID="):
            out.append(value[5:])
    return out


def _with_id(uuid: str) -> list[str]:
    done = subprocess.run(["blkid", "-t", f"UUID={uuid}", "-o", "device"], capture_output=True, text=True)
    return [line.strip() for line in done.stdout.splitlines() if line.strip()]


def stick() -> set[str]:
    sources = {s for s in (_source(BOOT), _source(str(PLACES[0]))) if s}
    for uuid in _boot_ids():
        sources.update(_with_id(uuid))
    found = set()
    for source in sources:
        found |= setup_disks.disks_in(setup_disks._lsblk("-s", source))
    return found


def targets() -> list:
    skip = stick() | setup_disks.system_disks()
    return setup_disks.listing(setup_disks._lsblk("-e7"), skip)
