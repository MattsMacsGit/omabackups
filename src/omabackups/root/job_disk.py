"""Root jobs for a backup disk on this computer, and Start over (D28).

create-disk: erase the disk the user picked (checked again: still the same
one), one partition "OmaBackups", then the backup box on it through the
local gatekeeper (the same code as on a server), proved to open with this
computer's key. Only then is the disk recorded as the backup location.
start-over: forget the backup location; delete nothing in the backup.
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from omabackups.backup.source import Snapshots, parts
from omabackups.core import ids, paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic
from omabackups.root import keys
from omabackups.setup import bundle, disks
from omabackups.where.disk import LocalGate, local_env


def _run(*cmd: str, data: str | None = None) -> str:
    done = subprocess.run(list(cmd), input=data, capture_output=True, text=True)
    if done.returncode != 0:
        raise OmaError("Setting up the backup disk stopped.",
                       "If something is using the disk (a file manager window, say), close "
                       "it and try again.", f"{' '.join(cmd)}: {done.stderr.strip()}",
                       code="disk-failed")
    return done.stdout


def prepare(device: str) -> str:
    """Erase the disk: one GPT partition named OmaBackups. Returns its path."""
    if os.environ.get("OMABACKUPS_SYSROOT"):   # tests: a folder stands in for the partition
        return str(Path(device) / "part1")
    tree = json.loads(_run("lsblk", "-J", "-o", "PATH,MOUNTPOINTS", device))
    for node in tree["blockdevices"]:
        for child in [node, *node.get("children", [])]:
            for grandchild in [child, *child.get("children", [])]:
                for mount in grandchild.get("mountpoints") or []:
                    if mount:
                        _run("umount", mount)
    _run("wipefs", "-a", "-q", device)
    _run("sfdisk", "--quiet", "--wipe", "always", "--wipe-partitions", "always", device,
         data="label: gpt\nsize=+, type=linux, name=OmaBackups\n")
    # The new partition takes a moment to appear (the kernel re-reads the
    # disk, then udev makes its names): wait for it rather than look once.
    for _ in range(30):
        subprocess.run(["udevadm", "settle", "--timeout=5"], capture_output=True)
        part = _first_partition(json.loads(_run("lsblk", "-J", "-o", "NAME,PATH,TYPE,PARTUUID", device)))
        if part.get("partuuid"):
            stable = Path("/dev/disk/by-partuuid") / part["partuuid"]
            if stable.exists():
                return str(stable)
        subprocess.run(["partx", "-u", device], capture_output=True)
        time.sleep(0.5)
    raise OmaError("The disk was erased, but its new partition didn't appear.",
                   "Unplug the disk, plug it back in, and run setup disk again.",
                   device, code="disk-failed")


def _first_partition(tree: dict) -> dict:
    """lsblk lists partitions inside their disk or next to it, depending on
    the columns asked for: look everywhere."""
    def walk(nodes):
        for node in nodes:
            if node.get("type") == "part":
                return node
            found = walk(node.get("children") or [])
            if found:
                return found
        return None
    return walk(tree.get("blockdevices", [])) or {}


def _gate_admin(*args: str, data: str = "") -> None:
    done = subprocess.run([sys.executable, str(bundle.gate_file()), "admin", *args], input=data,
                          capture_output=True, text=True, env=local_env())
    if done.returncode != 0:
        raise OmaError("Setting up the backup disk stopped.", "Try again.",
                       done.stderr.strip(), code="disk-failed")


def create_disk(request: dict) -> dict:
    device, password = str(request.get("device", "")), request.get("password")
    if not isinstance(password, str) or not password:
        raise OmaError("Your backup's password is missing.", code="bad-request")
    if not os.environ.get("OMABACKUPS_SYSROOT"):
        disk = disks.find(device)
        if disk is None or disk.size != request.get("size") or disk.model != request.get("model"):
            raise OmaError("That disk isn't the one you picked any more (was it unplugged?).",
                           "Nothing was erased. Run setup disk again.", device, code="bad-request")
    partition = prepare(device)

    pub = keys.ensure()
    _gate_admin("init", str(paths.system_state_dir() / "disk-gate" / "store"))
    _gate_admin("add-computer", ids.system_id(), "this computer", data=pub)
    gate = LocalGate(pub)
    secrets = json.dumps({"password": password,
                          "key": base64.b64encode(keys.read_unlock_key()).decode()})
    made = gate.call("create-disk", partition, data=secrets.encode())
    bid = made["id"]
    gate.call("unlock", bid, data=keys.read_unlock_key())
    inside = gate.call("points", bid)
    gate.call("lock", bid)
    if inside.get("lines", [{}])[0].get("line") != "001":
        raise OmaError("The new backup on the disk doesn't look right.", "Run setup disk again.",
                       json.dumps(inside)[:500], code="bad-backup")
    size = int(request.get("size") or 0)
    write_atomic(paths.server_file(), (json.dumps(
        {"kind": "disk", "device": partition, "backup": bid, "cipher": made["cipher"],
         "size": size, "model": request.get("model", ""), "set_up": int(time.time())},
        indent=2) + "\n").encode(), 0o644)
    return {"backup": bid, "cipher": made["cipher"], "size": size}


def start_over(request: dict) -> dict:
    """D28: forget the backup location and this computer's local snapshots."""
    try:
        kind = json.loads(paths.server_file().read_text()).get("kind", "server")
    except (OSError, ValueError):
        kind = None
    if not os.environ.get("OMABACKUPS_SYSROOT"):
        for part in parts():
            if part.btrfs:
                with Snapshots(part.device) as snaps:
                    for name in snaps.names():
                        snaps.drop(name)
    for path in (paths.server_file(), paths.system_state_dir() / "backup.json",
                 paths.system_state_dir() / "health.json", paths.system_run_dir() / "progress.json",
                 paths.known_hosts_file()):
        path.unlink(missing_ok=True)
    shutil.rmtree(paths.system_state_dir() / "disk-gate", ignore_errors=True)
    return {"forgot": kind}
