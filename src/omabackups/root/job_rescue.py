"""Root jobs for the Rescue USB (9c, D11, 5.7), as root:

rescue-usb-write    the downloaded image onto the stick, then its small
                    settings part (OMABACKUPS): the server's addresses, its
                    fingerprint and the stick's own read-only key (the last
                    stick's key is taken off the server)
rescue-usb-refresh  only the settings part rewritten (a new key, the old cut off)

Every disk can be chosen (warn, never block), except the one this system
runs on. Progress goes to /run/omabackups/rescue-usb.json for the window
that started it.
"""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from omabackups.core import paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic

LABEL = "OMABACKUPS"
SETTINGS_SIZE = "64M"


def progress_file() -> Path:
    return paths.system_run_dir() / "rescue-usb.json"


def _say(step: str, percent: int = 0) -> None:
    paths.system_run_dir().mkdir(parents=True, exist_ok=True)
    write_atomic(progress_file(), (json.dumps({"step": step, "percent": percent}) + "\n").encode(), 0o644)


def _run(*cmd: str, data: bytes | None = None) -> str:
    done = subprocess.run(list(cmd), input=data, capture_output=True)
    if done.returncode != 0:
        raise OmaError(f"Making the Rescue USB failed ({cmd[0]}).",
                       "Unplug the stick, plug it in again, and try again.",
                       (done.stderr or done.stdout).decode("utf-8", "replace").strip()[-1500:], code="rescue-usb")
    return done.stdout.decode("utf-8", "replace").strip()


def _disk(request: dict) -> str:
    from omabackups.setup import disks
    disk = str(request.get("disk", ""))
    if not disk.startswith("/dev/") or disks.find(disk) is None:
        raise OmaError("That isn't a disk this computer can write a Rescue USB to.",
                       "Choose the stick again from the list.", disk, code="bad-request")
    return disk


def _image(request: dict) -> Path:
    """Only the image in the linked user's own download folder."""
    import pwd
    from omabackups.backup.run import linked_user
    from omabackups.setup.rescue_image import NAME
    home = Path(pwd.getpwnam(linked_user()).pw_dir)
    image = Path(str(request.get("image", ""))).resolve()
    if image.name != NAME or not image.is_file() or home not in image.parents:
        raise OmaError("The rescue system to write wasn't found.", "Make the Rescue USB again.",
                       str(image), code="bad-request")
    return image


def _copy(image: Path, disk: str) -> None:
    total, done = image.stat().st_size, 0
    with open(image, "rb") as src, open(disk, "wb", buffering=0) as dst:
        while block := src.read(4 << 20):
            dst.write(block)
            done += len(block)
            _say("write", int(100 * done / total))
        os.fsync(dst.fileno())


def _reread(disk: str) -> None:
    if subprocess.run(["blockdev", "--rereadpt", disk], capture_output=True).returncode != 0:
        subprocess.run(["partx", "-u", disk], capture_output=True)
    subprocess.run(["udevadm", "settle"], capture_output=True)


def _settings_part(disk: str) -> str | None:
    listing = subprocess.run(["lsblk", "-nrpo", "NAME,LABEL", disk], capture_output=True, text=True).stdout
    return next((line.split()[0] for line in listing.splitlines()
                 if len(line.split()) > 1 and line.split()[1] == LABEL), None)


def _write_settings(part: str) -> dict:
    """A new read-only key on the server (the last stick's taken off), its
    settings onto the stick's settings part."""
    from omabackups.rescue import settings
    from omabackups.where import location
    server = location.load()
    if server.get("kind") == "disk" or server.get("migrating"):
        raise OmaError("A Rescue USB needs this computer's backup on a backup server.",
                       "Set up backups to a server first (a disk rescue comes later).", code="no-server")
    gate, _away = location.connect(server)
    gate.check_version()
    bundle = settings.make(gate, server)
    with tempfile.TemporaryDirectory(prefix="omabackups-stick.") as mnt:
        _run("mount", part, mnt)
        try:
            for name in settings.FILES:
                Path(mnt, name).write_text(bundle[name])     # FAT: no owners or modes to keep
        finally:
            subprocess.run(["sync"])
            _run("umount", mnt)
    return json.loads(bundle["rescue.json"])


def write(request: dict) -> dict:
    from omabackups.restore import newdisk
    disk, image = _disk(request), _image(request)
    if image.stat().st_size > int(_run("blockdev", "--getsize64", disk)) - (80 << 20):
        raise OmaError("That stick is too small for the rescue system.", "Use a stick of 4 GB or more.",
                       code="rescue-usb-small")
    _say("write")
    newdisk.free(disk)
    _copy(image, disk)
    _say("settings", 100)
    _reread(disk)
    # The image's own table is the old (MBR) kind with two parts: a third,
    # small, after them, holds the settings.
    _run("sfdisk", "--append", "--no-reread", disk, data=f",{SETTINGS_SIZE},c\n".encode())
    _reread(disk)
    part = newdisk.partition(disk, 3)
    for _ in range(20):
        if os.path.exists(part):
            break
        time.sleep(0.5)
    _run("mkfs.fat", "-n", LABEL, part)
    made = _write_settings(part)
    _say("done", 100)
    return {"made": made, "disk": disk}


def refresh(request: dict) -> dict:
    from omabackups.restore import newdisk
    disk = _disk(request)
    part = _settings_part(disk)
    if not part:
        raise OmaError("That stick isn't a Rescue USB (it has no settings part).",
                       "Make Rescue USB writes a new one.", disk, code="rescue-usb-not-one")
    newdisk.free(disk)
    return {"made": _write_settings(part), "disk": disk}
