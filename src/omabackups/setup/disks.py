"""Every disk, with a plain warning of what's on it (the rule: warn, never
block, never hide a disk, never choose one for the user). Only the disk the
running system is on is left out: you can't erase what you're running from.
"""

import json
import subprocess
from dataclasses import dataclass, field

from omabackups.backup.check import human

COLUMNS = "NAME,PATH,SIZE,MODEL,TRAN,TYPE,RM,FSTYPE,LABEL,PARTLABEL,MOUNTPOINTS,PARTUUID"
FORMATS = {"apfs": "formatted for a Mac (APFS)", "hfsplus": "formatted for a Mac (HFS+)",
           "ntfs": "formatted for Windows (NTFS)", "vfat": "FAT", "exfat": "exFAT",
           "ext4": "Linux (ext4)", "btrfs": "Linux (btrfs)", "crypto_LUKS": "encrypted (LUKS)",
           "swap": "swap", "xfs": "Linux (XFS)"}


@dataclass
class Disk:
    path: str
    size: int
    model: str
    transport: str
    removable: bool
    warnings: list = field(default_factory=list)

    def line(self) -> str:
        what = f"{self.model or 'disk'} ({self.transport or 'internal'})"
        return f"{self.path}  {human(self.size)}  {what}"


def _lsblk(*args: str) -> dict:
    done = subprocess.run(["lsblk", "-J", "-b", "-o", COLUMNS, *args], capture_output=True, text=True)
    return json.loads(done.stdout or '{"blockdevices": []}')


def system_disks() -> set[str]:
    """The disk(s) the running system is on (through encryption and LVM)."""
    source = subprocess.run(["findmnt", "-n", "-o", "SOURCE", "/"], capture_output=True,
                            text=True).stdout.strip().split("[")[0]
    return disks_in(_lsblk("-s", source))


def disks_in(tree: dict) -> set[str]:
    """The whole disks in an inverse lsblk tree (what something is on)."""
    found = set()

    def walk(node):
        if node.get("type") == "disk":
            found.add(node["path"])
        for child in node.get("children", []):
            walk(child)
    for node in tree.get("blockdevices", []):
        walk(node)
    return found


# Names 1.x (and 2.0) give their disks: a disk with one of these is somebody's backup.
OMABACKUPS_NAMES = {"OmaBackups", "OmaRescue", "OMABOOT", "OmaNetRescue", "OMANETBOOT",
                    "OmaNetKeys", "OMARCHY-BACKUPS", "OMARCHY-TM", "OmaBackups-store",
                    "omabackups-store"}


def _describe(node: dict, warnings: list) -> None:
    for part in node.get("children", []):
        bits = [FORMATS.get(part.get("fstype") or "", part.get("fstype") or "unknown contents")]
        if part.get("label"):
            bits.append(f'named "{part["label"]}"')
        mounts = [m for m in part.get("mountpoints") or [] if m]
        if mounts:
            bits.append(f"in use: mounted at {', '.join(mounts)} (it will be unmounted)")
        if part.get("fstype") == "crypto_LUKS":
            bits.append("can't see inside: it may hold a system or files")
        warnings.append(f"{part['path']} ({human(int(part['size']))}): " + ", ".join(bits))


def disks() -> list[Disk]:
    return listing(_lsblk("-e7"), system_disks())     # -e7: leave out loop devices


def listing(tree: dict, skip: set[str]) -> list[Disk]:
    """Every disk in an lsblk tree (this computer's or a server's), with warnings."""
    out = []
    for node in tree.get("blockdevices", []):
        if node.get("type") != "disk" or node["path"] in skip or int(node["size"] or 0) == 0:
            continue
        if node["name"].startswith(("zram", "ram")):
            continue    # memory, not a disk
        disk = Disk(node["path"], int(node["size"]), (node.get("model") or "").strip(),
                    node.get("tran") or "", bool(node.get("rm")))
        if disk.transport in ("nvme", "sata", "ata", "") and not disk.removable:
            disk.warnings.append("This is your computer's internal drive.")
        names = {c.get(k) for c in node.get("children") or [] for k in ("label", "partlabel")}
        if names & OMABACKUPS_NAMES:
            disk.warnings.append("This looks like an OmaBackups backup disk: "
                                 "someone's backups may be on it.")
        if not node.get("children"):
            disk.warnings.append("No partitions found (it may still hold data).")
        _describe(node, disk.warnings)
        disk.warnings.append("Everything on it will be erased.")
        out.append(disk)
    return out


def find(path: str) -> Disk | None:
    return next((d for d in disks() if d.path == path), None)
