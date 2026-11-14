"""Is this computer set up the way Omarchy installs it? (audit 7.5; 1.x
lib/detect.py.) Checked at setup: warn, never block. Backups and Browse work
anywhere; a Rescue USB needs an encrypted btrfs disk with a separate boot
partition. Wording agreed 14 Nov."""

import os
from pathlib import Path

TITLE = "This computer isn't set up the way Omarchy installs it"
TEXT = ("Backups and Browse work, but a Rescue USB can't bring it back: that needs an encrypted "
        "btrfs disk with a separate boot partition, as Omarchy's installer makes.")
NOT_BTRFS = "The system isn't on btrfs."
HOME_ELSEWHERE = "Your home folder isn't on the same disk as the system."
NO_BOOT = "There's no separate boot partition."
NOT_ENCRYPTED = "The disk isn't encrypted."


def mounts(text: str) -> dict:
    """{mount point: (filesystem, source)} from /proc/self/mountinfo."""
    out = {}
    for row in text.splitlines():
        if " - " not in row:
            continue
        left, right = row.split(" - ", 1)
        lbits, rbits = left.split(), right.split()
        if len(lbits) > 4 and len(rbits) > 1:
            out[lbits[4]] = (rbits[0], rbits[1])
    return out


def encrypted(source: str, sysroot: Path = Path("/")) -> bool:
    """The system's disk is a dm-crypt (LUKS) mapping."""
    if not source.startswith("/dev/mapper/") and not source.startswith("/dev/dm-"):
        return False
    dm = os.path.basename(os.path.realpath(source)) if sysroot == Path("/") else source.rsplit("/", 1)[-1]
    try:
        return (sysroot / "sys/block" / dm / "dm/uuid").read_text().startswith("CRYPT-")
    except OSError:
        return False


def problems(mountinfo: str | None = None, sysroot: Path = Path("/")) -> list[str]:
    if mountinfo is None:
        try:
            mountinfo = Path("/proc/self/mountinfo").read_text()
        except OSError:
            return []
    found = mounts(mountinfo)
    root, home, boot = found.get("/"), found.get("/home"), found.get("/boot")
    out = []
    if not root or root[0] != "btrfs":
        out.append(NOT_BTRFS)
    if root and (not home or home[1] != root[1]):
        out.append(HOME_ELSEWHERE)
    if not boot or boot[0] not in ("vfat", "msdos") or (root and boot[1] == root[1]):
        out.append(NO_BOOT)
    if root and not encrypted(root[1], sysroot):
        out.append(NOT_ENCRYPTED)
    return out


def ask() -> None:
    """At setup: say what doesn't fit, then Carry on or Stop."""
    from omabackups.core.errors import OmaError
    from omabackups.setup import menu
    if os.environ.get("OMABACKUPS_SYSROOT"):
        return                                   # tests: not this computer's disks
    found = problems()
    if not found:
        return
    menu.title(TITLE, TEXT + "\n\n" + "\n".join(found))
    if not menu.confirm("Carry on?", yes="Carry on", no="Stop"):
        raise OmaError(menu.CANCELLED, code="cancelled")
