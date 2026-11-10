"""The disks a rescue can go onto: every disk, each with what's on it (the
rule: warn, never block, never hide one), except the stick the rescue is
running from (archiso mounts it at /run/archiso/bootmnt) and anything the
running system is on.
"""

import subprocess

from omabackups.setup import disks as setup_disks

BOOT = "/run/archiso/bootmnt"


def stick() -> set[str]:
    source = subprocess.run(["findmnt", "-n", "-o", "SOURCE", BOOT], capture_output=True,
                            text=True).stdout.strip()
    return setup_disks.disks_in(setup_disks._lsblk("-s", source)) if source else set()


def targets() -> list:
    skip = stick() | setup_disks.system_disks()
    return setup_disks.listing(setup_disks._lsblk("-e7"), skip)
