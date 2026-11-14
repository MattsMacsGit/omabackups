"""Quick Rescue and Full Rescue (6.1 G, stage 9b): a restore point onto a
disk, so it starts and unlocks. 1.x's restore-to-disk.sh, step by step:

  connect   your backup opened with its password (the stick's key reads only)
  disk      the new disk prepared (newdisk.py)
  system    the system part onto @ (no swap, no tmp)
  settings  the home part onto @home: Full = everything; Quick = the hidden
            files and folders, the visible ones left empty for Restore my files,
            and what can be fetched again (caches, VMs, AI models, games) left
  boot      the boot part onto the boot partition; a failed copy stops it
  start     the boot checklist (bootfix.py): fstab, crypttab, the boot
            loader's settings, startup files rebuilt and Limine installed
            inside the restored system, the fallback boot file, the boot
            entry patched and VERIFIED, a firmware entry, the point recorded

Every step reports how far it is (phase, fraction, status line) for
Omarchy's progress screen. A failure tidies up and says what happened.
"""

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from omabackups.core import log
from omabackups.core.errors import OmaError
from omabackups.restore import bootfix, newdisk
from omabackups.restore.later import LATER
from omabackups.restore.later import system_paths as later_paths

PERCENT = re.compile(rb"(\d+)%")
SYSTEM_SKIP = ("/swap", "/swapfile", "/tmp", "/var/tmp")
# What a Quick Rescue leaves for Restore my files: things that can be fetched
# or made again, whatever they weigh (1.x: a size limit broke installed tools):
# caches and trash, and the big part of the Quick skips items (restore/later.py;
# a program's settings, logins and saves come back now).
HOME_JUNK = (".cache", ".thumbnails", ".var/app/*/cache", ".local/share/Trash", ".Trash", "lost+found")


def home_later_excludes() -> list[str]:
    """rsync excludes, relative to the home part (/<user>/...)."""
    from omabackups.restore.later import home_rules
    rules = list(HOME_JUNK) + [r for rs in home_rules("").values() for r in rs]
    return [f"--exclude={r}" if r.startswith("**/") else f"--exclude=/*/{r.lstrip('/')}" for r in rules]
PHASES = (("connect", 3), ("disk", 4), ("system", 45), ("settings", 25), ("boot", 3), ("start", 10))
FULL_PHASES = (("connect", 2), ("disk", 3), ("system", 30), ("settings", 55), ("boot", 2), ("start", 8))


def home_filter(full: bool) -> list[str]:
    if full:
        return []
    out = home_later_excludes()          # excludes first: rsync takes the first match
    return out + ["--include=/*/", "--include=/*/.*", "--include=/*/.*/**", "--include=/*/*/", "--exclude=/*/**"]


FULL_COPY = ("-aHAX", "--numeric-ids")      # links, ACLs, attributes, owners by number: as backed up
FAT_COPY = ("-rlt",)                       # the boot partition is FAT: no owners, no attributes


def fetch(gate, bid: str, point: str, part: str, dest: Path, extra: list[str], report,
          flags: tuple = FULL_COPY) -> int:
    """One part of the restore point onto the new disk; report(fraction)."""
    command = ["rsync", *flags, "--info=progress2", "--no-inc-recursive", *extra,
               "-e", gate.rsh(), f"--rsync-path=fetch {bid} {point} {part}",
               f"{gate.rsync_target()}:{part}/", f"{dest}/"]
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=gate.rsync_env())
    buffer = b""
    while chunk := proc.stdout.read1(4096):
        buffer = (buffer + chunk)[-400:]
        if found := PERCENT.findall(buffer):
            report(min(100, int(found[-1])) / 100)
    error = proc.stderr.read().decode("utf-8", "replace")
    code = proc.wait()
    if code not in (0, 23, 24):     # 23/24: an attribute not copied, a file gone: fine (1.x)
        raise OmaError(f"Your {part} couldn't be brought back from the backup.",
                       "The disk was only partly written. Run the rescue again: it starts from the beginning.",
                       error.strip()[-2000:] or f"rsync exit {code}", code="rescue-copy")
    return code


def _chroot(root: Path, *cmd: str) -> bool:
    return subprocess.run(["arch-chroot", str(root), *cmd], capture_output=True).returncode == 0


def make_it_start(new, root: Path, point: str, full: bool, say) -> list[str]:
    """The boot checklist, 2-9. Returns notes for the end screen."""
    notes = []
    ids = new.ids()
    say(0.1, "Pointing the system at the new disk")
    bootfix.settings_files(newdisk.ROOT / "@", ids["partuuid"], ids["luks"], ids["btrfs"], ids["esp"])
    newdisk.mount_system(new)
    say(0.3, "Rebuilding the startup files")
    if not _chroot(root, "bash", "-lc", "command -v limine-mkinitcpio >/dev/null && limine-mkinitcpio"):
        _chroot(root, "bash", "-lc", "mkinitcpio -P && (limine-update || true)")
    say(0.6, "Installing the boot loader")
    _chroot(root, "limine-install")          # inside the restored system: never onto the stick (1.x)
    fallback = newdisk.ESP / "EFI/BOOT/BOOTX64.EFI"
    if not fallback.is_file():
        for src in (root / "usr/share/limine/BOOTX64.EFI", Path("/usr/share/limine/BOOTX64.EFI")):
            if src.is_file():
                fallback.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, fallback)
                break
    if not fallback.is_file():
        raise OmaError("The restored disk has no boot file (EFI/BOOT/BOOTX64.EFI), so it wouldn't start.",
                       "Run the rescue again. If it keeps happening, report it with the details.",
                       "limine-install didn't put it there and no copy was found", code="rescue-boot")
    say(0.8, "Checking it will unlock and start")
    try:
        bootfix.boot_entry(newdisk.ESP, root, ids["partuuid"], ids["luks"])
    except bootfix.BootFixError as exc:
        raise OmaError("The restored disk wouldn't unlock at start-up, so the rescue stopped.",
                       "Run the rescue again. If it keeps happening, report it with the details.",
                       str(exc), code="rescue-boot") from None
    if not _firmware_entry(new):
        notes.append("If this computer doesn't offer the disk at start-up, choose EFI/BOOT/BOOTX64.EFI "
                     "on it in the firmware's boot menu.")
    _record(root, point, full)
    return notes


def _firmware_entry(new) -> bool:
    """The computer's own boot list (efibootmgr), if it has none for this disk."""
    if not Path("/sys/firmware/efi").is_dir() or not shutil.which("efibootmgr"):
        return False
    listed = subprocess.run(["efibootmgr"], capture_output=True, text=True).stdout.lower()
    esp_part = newdisk.blkid(new.esp, "PARTUUID").lower()
    if esp_part and esp_part in listed:
        return True
    return subprocess.run(["efibootmgr", "--create", "--disk", new.disk, "--part", "1", "--label", "Omarchy",
                           "--loader", "\\EFI\\BOOT\\BOOTX64.EFI"], capture_output=True).returncode == 0


def _record(root: Path, point: str, full: bool) -> None:
    """Checklist 9, and Quick's Restore my files: which point this came
    from; each home's panel offers Restore my files until its folders are back."""
    state = root / "var/lib/omabackups"
    state.mkdir(parents=True, exist_ok=True)
    (state / "rescued.json").write_text(json.dumps({"point": point, "full": full, "at": int(time.time())}) + "\n")
    # Automatic backups wait for a Back up now (D29; audit 1.2: on 13 Nov a
    # rescued system backed up two minutes after it started). The record came
    # back with the system: what it knew about earlier restores doesn't apply.
    try:
        record = json.loads((state / "backup.json").read_text())
    except (OSError, ValueError):
        record = {}
    record = {k: v for k, v in record.items() if k != "forced_past"}
    (state / "backup.json").write_text(json.dumps({**record, "automatic_paused": True}, indent=2) + "\n")
    (state / "restored.json").unlink(missing_ok=True)
    for home in sorted((root / "home").iterdir()) if (root / "home").is_dir() else []:
        if not home.is_dir() or home.name.startswith("."):
            continue
        folders = sorted(p.name for p in home.iterdir() if p.is_dir() and not p.name.startswith("."))
        mine = home / ".local/state/omabackups"
        mine.mkdir(parents=True, exist_ok=True)
        (mine / "migrate.json").write_text(json.dumps(
            {"done": True, "files_restored": full, "point": point, "from_user": home.name,
             "files": [] if full else folders, "later": [] if full else list(LATER),
             "restart": False, "rescued": True,
             "at": int(time.time()), "version": 1}, indent=2) + "\n")
        owner = home.stat()
        for p in (home / ".local", home / ".local/state", mine, mine / "migrate.json"):
            os.lchown(p, owner.st_uid, owner.st_gid)


def rescue(gate, bid: str, password: str, point: str, full: bool, disk: str, disk_password: str,
           show, newest: bool = False) -> dict:
    """The whole rescue. show(phase, fraction, status). Returns notes for the end."""
    logger = log.get("rescue")
    from omabackups.backup.run import HoldKeeper
    show("connect", 0, "Connecting to your backup")
    hold = gate.call("unlock", bid, data=password.encode())["hold"]
    keeper = HoldKeeper(gate, bid, hold, logger)
    started = False
    try:
        show("disk", 0, "Preparing the disk")
        started = True
        new = newdisk.prepare(disk, disk_password)
        show("disk", 1, "Preparing the disk")
        later = [] if full else later_paths()            # AI models and the like: later (audit 8.4)
        fetch(gate, bid, point, "system", newdisk.ROOT / "@",
              [f"--exclude={p}" for p in (*SYSTEM_SKIP, *later)] + ["--delete"],
              lambda f: show("system", f, "Bringing back your system"))
        what = "Bringing back your files" if full else "Bringing back your settings"
        fetch(gate, bid, point, "home", newdisk.ROOT / "@home", home_filter(full) + ["--delete"],
              lambda f: show("settings", f, what))
        show("boot", 0, "Bringing back the boot files")
        fetch(gate, bid, point, "boot", newdisk.ESP, ["--delete-delay"],
              lambda f: show("boot", f, "Bringing back the boot files"), FAT_COPY)
        if newest:          # the first backup after the rescue is quick (seed.py)
            try:
                from omabackups.restore import seed
                seed.seed(newdisk.ROOT, point, full)
            except (OSError, subprocess.CalledProcessError) as exc:
                logger.warning("no snapshots for the first backup (it checks every file): %s", exc)
        notes = make_it_start(new, newdisk.ROOT, point, full,
                              lambda f, status: show("start", f, status))
        logger.info("rescue from %s onto %s done (%s)", point, disk, "full" if full else "quick")
        return {"done": True, "notes": notes}
    except OmaError as exc:
        logger.warning("rescue failed: %s %s", exc.what, exc.details)
        if started:
            exc.todo = exc.todo or "The disk was only partly written. Run the rescue again."
        raise
    finally:
        newdisk.close()
        keeper.stop()
        try:
            gate.call("lock", bid, hold)
        except OmaError:
            pass
