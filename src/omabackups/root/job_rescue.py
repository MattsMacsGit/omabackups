"""Root jobs for the Rescue USB (9c, D11, 5.7), as root:

rescue-usb-write    the downloaded image onto the stick, then its small
                    settings part (OMABACKUPS): the server's addresses, its
                    fingerprint and the stick's own read-only key (the last
                    stick's key is taken off the server)
rescue-usb-refresh  only the settings part rewritten (a new key, the old cut off)

The settings part is encrypted (LUKS2, labelled OMABACKUPS) with the backup's
own password: one password opens the stick and the backup (audit 8.3, agreed
14 Nov). It's checked against the backup first, so a typo never locks a stick.

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

from omabackups.core import mounts, paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic

LABEL = "OMABACKUPS"
MAPPER = "omabackups-stick-settings"
SETTINGS_SIZE = "64M"
# Blanked just past the image, where the settings part goes (the size check
# keeps this much room): an old stick's settings part found there again is
# opened by the desktop the moment it reappears, and can't be formatted.
CLEAR = 80 << 20


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
        zeros, left = bytes(4 << 20), CLEAR
        while left > 0:
            left -= dst.write(zeros[:min(len(zeros), left)])
        os.fsync(dst.fileno())


def _reread(disk: str) -> None:
    if subprocess.run(["blockdev", "--rereadpt", disk], capture_output=True).returncode != 0:
        subprocess.run(["partx", "-u", disk], capture_output=True)
    subprocess.run(["udevadm", "settle"], capture_output=True)


def _let_go(part: str) -> None:
    for _ in range(5):
        if subprocess.run(["findmnt", "-S", part], capture_output=True).returncode != 0:
            return
        mounts.let_go(part)


def _format(part: str, password: str) -> str:
    """The settings part locked with the backup's password (LUKS2), FAT
    inside; returns the opened inside. The desktop may open a stick's part
    as soon as it appears: let go of it and try again before giving up."""
    subprocess.run(["cryptsetup", "close", MAPPER], capture_output=True)
    command = ["cryptsetup", "luksFormat", "--type", "luks2", "--label", LABEL, "--batch-mode",
               "--key-file=-", part]
    for _ in range(9):
        _let_go(part)
        if subprocess.run(command, input=password.encode(), capture_output=True).returncode == 0:
            break
        time.sleep(1)
    else:
        _let_go(part)
        _run(*command, data=password.encode())
    _run("cryptsetup", "open", "--key-file=-", part, MAPPER, data=password.encode())
    inside = f"/dev/mapper/{MAPPER}"
    _run("mkfs.fat", "-n", LABEL, inside)
    return inside


def check_password(request: dict) -> str:
    """The backup's password, tried on the backup before anything is written."""
    from omabackups.where import location
    password = request.get("password")
    if not isinstance(password, str) or not password:
        raise OmaError("The Rescue USB is locked with your backup's password, and none was given.",
                       "Make or refresh it again and type your backup's password.", code="bad-request")
    server = location.load()
    gate, _away = location.connect(server)
    try:
        hold = gate.call("unlock", server["backup"], data=password.encode())["hold"]
    except OmaError as exc:
        raise OmaError("That password didn't open your backup, so the stick wasn't touched.",
                       "Try again with your backup's password.", exc.details, code="wrong-password") from None
    gate.call("lock", server["backup"], hold)
    return password


def _settings_part(disk: str) -> str | None:
    listing = subprocess.run(["lsblk", "-nrpo", "NAME,LABEL", disk], capture_output=True, text=True).stdout
    return next((line.split()[0] for line in listing.splitlines()
                 if len(line.split()) > 1 and line.split()[1] == LABEL), None)


def _write_settings(part: str, password: str) -> dict:
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
    inside = _format(part, password)
    try:
        with tempfile.TemporaryDirectory(prefix="omabackups-stick.") as mnt:
            _run("mount", inside, mnt)
            try:
                for name in settings.FILES:
                    Path(mnt, name).write_text(bundle[name])     # FAT: no owners or modes to keep
            finally:
                subprocess.run(["sync"])
                _run("umount", mnt)
    finally:
        subprocess.run(["cryptsetup", "close", MAPPER], capture_output=True)
    return json.loads(bundle["rescue.json"])


def write(request: dict) -> dict:
    from omabackups.restore import newdisk
    disk, image = _disk(request), _image(request)
    password = check_password(request)
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
    _run("sfdisk", "--append", "--no-reread", disk, data=f",{SETTINGS_SIZE},83\n".encode())
    _reread(disk)
    part = newdisk.partition(disk, 3)
    for _ in range(20):
        if os.path.exists(part):
            break
        time.sleep(0.5)
    made = _write_settings(part, password)
    _say("done", 100)
    return {"made": made, "disk": disk}


def refresh(request: dict) -> dict:
    from omabackups.restore import newdisk
    disk = _disk(request)
    password = check_password(request)
    part = _settings_part(disk)
    if not part:
        raise OmaError("That stick isn't a Rescue USB (it has no settings part).",
                       "Make Rescue USB writes a new one.", disk, code="rescue-usb-not-one")
    newdisk.free(disk)
    return {"made": _write_settings(part, password), "disk": disk}
