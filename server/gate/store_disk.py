"""A backup store on a disk of its own (D5, BUILD 6.1 C): the disk the user
picked is erased, gets one partition with a plain ext4 filesystem, and is
mounted by OmaBackups' own mount unit (no edits to the server's fstab).
The backup boxes then live on it as on any store folder.
"""

import json
import subprocess
import time
from pathlib import Path

from registry import Refused

MOUNT = Path("/var/lib/omabackups-gate/disk-store")
LABEL = "omabackups-store"


def _run(*cmd: str, data: str | None = None) -> str:
    done = subprocess.run(list(cmd), input=data, capture_output=True, text=True)
    if done.returncode != 0:
        raise Refused(f"setting up the disk stopped at {cmd[0]}: {done.stderr.strip()[-300:]}")
    return done.stdout


def _system_disks() -> set[str]:
    source = _run("findmnt", "-n", "-o", "SOURCE", "/").strip().split("[")[0]
    found = set()

    def walk(nodes):
        for node in nodes:
            if node.get("type") == "disk":
                found.add(node["path"])
            walk(node.get("children") or [])
    walk(json.loads(_run("lsblk", "-J", "-s", "-o", "NAME,PATH,TYPE", source))["blockdevices"])
    return found


def _partition(device: str) -> dict:
    def walk(nodes):
        for node in nodes:
            if node.get("type") == "part":
                return node
            found = walk(node.get("children") or [])
            if found:
                return found
        return None
    return walk(json.loads(_run("lsblk", "-J", "-o", "NAME,PATH,TYPE,PARTUUID", device))
                ["blockdevices"]) or {}


def prepare(device: str, size: int) -> Path:
    """Erase `device` (checked: a whole disk, the size the user saw, not the
    server's own) and mount it as the backup store. Returns the store folder."""
    info = json.loads(_run("lsblk", "-J", "-b", "-d", "-o", "PATH,TYPE,SIZE", device))["blockdevices"]
    if not info or info[0]["type"] != "disk" or int(info[0]["size"]) != size:
        raise Refused("that disk isn't the one picked any more (was it unplugged?); nothing was erased")
    if device in _system_disks():
        raise Refused("that's the disk this server runs from")
    tree = json.loads(_run("lsblk", "-J", "-o", "NAME,PATH,MOUNTPOINTS", device))
    def unmount(nodes):
        for node in nodes:
            unmount(node.get("children") or [])
            for mount in node.get("mountpoints") or []:
                if mount:
                    _run("umount", mount)
    unmount(tree["blockdevices"])
    _run("wipefs", "-a", "-q", device)
    _run("sfdisk", "--quiet", "--wipe", "always", "--wipe-partitions", "always", device,
         data="label: gpt\nsize=+, type=linux, name=OmaBackups-store\n")
    for _ in range(30):
        subprocess.run(["udevadm", "settle", "--timeout=5"], capture_output=True)
        part = _partition(device)
        if part.get("partuuid") and Path(f"/dev/disk/by-partuuid/{part['partuuid']}").exists():
            break
        subprocess.run(["partx", "-u", device], capture_output=True)
        time.sleep(0.5)
    else:
        raise Refused("the disk was erased, but its new partition didn't appear; unplug it, "
                      "plug it back in, and run setup again")
    _run("mkfs.ext4", "-q", "-F", "-L", LABEL, "-m", "0", part["path"])
    MOUNT.mkdir(parents=True, exist_ok=True)
    unit = _run("systemd-escape", "-p", "--suffix=mount", str(MOUNT)).strip()
    Path("/etc/systemd/system", unit).write_text(
        "[Unit]\nDescription=OmaBackups backup store (a disk of its own)\n\n"
        f"[Mount]\nWhat=/dev/disk/by-partuuid/{part['partuuid']}\nWhere={MOUNT}\n"
        "Type=ext4\nOptions=noatime,nofail\n\n[Install]\nWantedBy=multi-user.target\n")
    _run("systemctl", "daemon-reload")
    _run("systemctl", "enable", "--now", unit)
    store = MOUNT / "store"
    store.mkdir(exist_ok=True)
    return store
