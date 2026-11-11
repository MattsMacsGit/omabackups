"""Letting go of a disk someone else mounted (the desktop opens sticks and
disks by itself, e.g. udiskie).

Root jobs run with their own view of the mounts (PrivateTmp in their unit):
an unmount there leaves the desktop's mount in place, the disk stays busy
("Device or resource busy"), and a disk written to while it's still mounted
can be written over again when the desktop lets go of it later. So other
people's mounts are unmounted in the computer's own view (PID 1's), with
nsenter (util-linux). Mounts a job makes itself stay in its own view: unmount
those with plain umount.
"""

import os
import subprocess


def private_view() -> bool:
    """True inside a root job's own mount view (False when that can't be told,
    e.g. not root, or on the Rescue USB where there's only one)."""
    try:
        return os.readlink("/proc/self/ns/mnt") != os.readlink("/proc/1/ns/mnt")
    except OSError:
        return False


def umount_command(*args: str) -> list[str]:
    if private_view():
        return ["nsenter", "--mount=/proc/1/ns/mnt", "--", "umount", *args]
    return ["umount", *args]


def let_go(*args: str) -> subprocess.CompletedProcess:
    """umount someone else's mount, everywhere it shows."""
    return subprocess.run(umount_command(*args), capture_output=True)
