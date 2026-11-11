"""The disk a rescue goes onto, set up as Omarchy sets up its own (1.x
restore-to-disk.sh): a 2 GB boot partition (FAT), the rest encrypted (LUKS2)
with btrfs inside and Omarchy's subvolumes (@, @home, @log, @pkg). As root,
on the Rescue USB. The password never goes on a command line.
"""

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from omabackups.core.errors import OmaError

ESP_SIZE = "2G"
MAPPER = "omabackups-restore"
ROOT = Path("/run/omabackups-restore/root")
ESP = Path("/run/omabackups-restore/esp")
MOUNTS = (("@home", "home"), ("@log", "var/log"), ("@pkg", "var/cache/pacman/pkg"))


def _run(*cmd: str, data: bytes | None = None) -> str:
    done = subprocess.run(list(cmd), input=data, capture_output=True)
    if done.returncode != 0:
        raise OmaError(f"Preparing the disk failed ({cmd[0]}).",
                       "Nothing was taken from your backup. Check the disk, then try again.",
                       (done.stderr or done.stdout).decode("utf-8", "replace").strip()[-1500:],
                       code="disk-failed")
    return done.stdout.decode("utf-8", "replace").strip()


def partition(disk: str, n: int) -> str:
    """/dev/sda -> /dev/sda1; /dev/nvme0n1 -> /dev/nvme0n1p1."""
    return f"{disk}p{n}" if disk[-1].isdigit() else f"{disk}{n}"


def blkid(dev: str, tag: str) -> str:
    return _run("blkid", "-s", tag, "-o", "value", dev)


@dataclass
class NewDisk:
    disk: str
    esp: str = ""
    luks: str = ""

    @property
    def mapper(self) -> str:
        return f"/dev/mapper/{MAPPER}"

    def ids(self) -> dict:
        ids = {"btrfs": blkid(self.mapper, "UUID"), "esp": blkid(self.esp, "UUID"),
               "partuuid": blkid(self.luks, "PARTUUID"), "luks": blkid(self.luks, "UUID")}
        if not all(ids.values()):
            raise OmaError("The new disk's IDs couldn't be read.", "Try the rescue again.",
                           str(ids), code="disk-failed")
        return ids


def free(disk: str) -> None:
    """Whatever is open or mounted on the disk lets go first (an open volume
    stops the partitioning with nothing to say why)."""
    listing = _run("lsblk", "-nrpo", "NAME,TYPE,MOUNTPOINTS", disk)
    for line in reversed(listing.splitlines()):
        parts = line.split(" ", 2)
        for mount in (parts[2].split("\\x0a") if len(parts) > 2 else []):
            if mount:
                subprocess.run(["umount", "-R", mount], capture_output=True)
        if len(parts) > 1 and parts[1] == "crypt":
            subprocess.run(["cryptsetup", "close", parts[0]], capture_output=True)


def _guid(disk: str, n: int) -> str:
    """The ID sgdisk just gave partition n (read from the disk itself)."""
    for line in _run("sgdisk", "-i", str(n), disk).splitlines():
        if line.startswith("Partition unique GUID:"):
            return line.split(":", 1)[1].strip().lower()
    return ""


def _seen(dev: str) -> str:
    done = subprocess.run(["lsblk", "-dno", "PARTUUID", dev], capture_output=True, text=True)
    return done.stdout.strip().lower()


def settle(new: NewDisk) -> None:
    """Nothing is written into the new layout until the computer sees it.
    The old partitions often sat at the same places, so /dev/sdX1 and 2 may
    exist all along: wait for the new partitions' own IDs, not their names.
    blockdev and partx are util-linux, always on the stick (partprobe wasn't)."""
    want = (_guid(new.disk, 1), _guid(new.disk, 2))
    for _ in range(30):
        if subprocess.run(["blockdev", "--rereadpt", new.disk], capture_output=True).returncode != 0:
            subprocess.run(["partx", "-u", new.disk], capture_output=True)
        here = [d for d in (new.disk, new.esp, new.luks) if os.path.exists(d)]
        subprocess.run(["udevadm", "trigger", "--action=change", *here], capture_output=True)
        subprocess.run(["udevadm", "settle"], capture_output=True)
        if all(want) and all(os.path.exists(p) for p in (new.esp, new.luks)) \
                and (_seen(new.esp), _seen(new.luks)) == want:
            return
        time.sleep(0.5)
    raise OmaError("The disk's new layout didn't show up.",
                   "Nothing was taken from your backup. Unplug the disk, plug it in again, and run the rescue again.",
                   f"wanted {new.esp}={want[0]} {new.luks}={want[1]}; "
                   f"seen {_seen(new.esp) or '-'} {_seen(new.luks) or '-'}", code="disk-failed")


def prepare(disk: str, password: str) -> NewDisk:
    """Wipe, partition, encrypt, format, make the subvolumes, mount them."""
    free(disk)
    subprocess.run(["wipefs", "-a", disk], capture_output=True)
    _run("sgdisk", "--zap-all", disk)
    _run("sgdisk", "-n", f"1:0:+{ESP_SIZE}", "-t", "1:ef00", "-c", "1:ESP",
         "-n", "2:0:0", "-t", "2:8309", "-c", "2:root", disk)
    new = NewDisk(disk, partition(disk, 1), partition(disk, 2))
    settle(new)
    for part in (new.esp, new.luks):        # what the old layout left at the same places
        subprocess.run(["wipefs", "-a", part], capture_output=True)
    _run("mkfs.fat", "-F32", "-n", "OMARCHY", new.esp)
    key = password.encode()
    _run("cryptsetup", "luksFormat", "--type", "luks2", "--batch-mode", "--key-file=-", new.luks, data=key)
    _run("cryptsetup", "open", "--key-file=-", new.luks, MAPPER, data=key)
    _run("mkfs.btrfs", "-f", "-L", "omarchy", new.mapper)
    ROOT.mkdir(parents=True, exist_ok=True)
    _run("mount", "-o", "compress=zstd:3", new.mapper, str(ROOT))
    for sub in ("@", "@home", "@log", "@pkg"):
        _run("btrfs", "subvolume", "create", str(ROOT / sub))
    # Never copied from the backup, so they'd stay 0700 root: pacman's download
    # user needs to get into the package cache (1.x lesson).
    os.chmod(ROOT / "@log", 0o755)
    os.chmod(ROOT / "@pkg", 0o755)
    ESP.mkdir(parents=True, exist_ok=True)
    _run("mount", new.esp, str(ESP))
    return new


def mount_system(new: NewDisk) -> Path:
    """The restored system as it will start: @ at the root, the others in
    place, the boot partition at /boot (for the steps run inside it)."""
    _run("umount", str(ROOT))
    _run("mount", "-o", "subvol=@,compress=zstd:3", new.mapper, str(ROOT))
    for sub, where in MOUNTS:
        (ROOT / where).mkdir(parents=True, exist_ok=True)
        _run("mount", "-o", f"subvol={sub},compress=zstd:3", new.mapper, str(ROOT / where))
    (ROOT / "boot").mkdir(exist_ok=True)
    (ROOT / "tmp").mkdir(exist_ok=True)
    _run("mount", "--bind", str(ESP), str(ROOT / "boot"))
    return ROOT


def close() -> None:
    """Everything let go, in order; never fails (it also runs after a failure)."""
    for where in ("boot", *(w for _, w in MOUNTS)):
        subprocess.run(["umount", str(ROOT / where)], capture_output=True)
    subprocess.run(["umount", "-R", str(ROOT)], capture_output=True)
    subprocess.run(["umount", str(ESP)], capture_output=True)
    if os.path.exists(f"/dev/mapper/{MAPPER}"):
        subprocess.run(["cryptsetup", "close", MAPPER], capture_output=True)
    subprocess.run(["sync"], capture_output=True)
