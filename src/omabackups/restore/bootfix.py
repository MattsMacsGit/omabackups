"""Making a restored disk start (stage 9b's boot checklist, 1.x
restore-to-disk.sh and lib/patch_boot_cmdline.py): the restored system's
settings still name the OLD disk; each is pointed at the new one, and the
boot entry is verified to unlock it before the rescue may say it worked.

Text in, text out where it can be, so every rule is tested.
"""

import re
import shutil
import subprocess
from pathlib import Path

HEX = r"[0-9a-fA-F-]+"


class BootFixError(Exception):
    pass


# --- fstab (checklist 2) -----------------------------------------------------

def fstab(text: str, btrfs_uuid: str, esp_uuid: str) -> str:
    """/, /home, /var/log, the package cache and /boot to the new disk; / and
    /boot must be there and rewritten; a swapfile line commented out (the new
    disk has none)."""
    wanted = {"/": ("btrfs", btrfs_uuid), "/home": ("btrfs", btrfs_uuid), "/var/log": ("btrfs", btrfs_uuid),
              "/var/cache/pacman/pkg": ("btrfs", btrfs_uuid), "/boot": ("vfat", esp_uuid)}
    boot_types = {"vfat", "fat", "msdos"}
    seen, problems, out = set(), [], []
    for line in text.splitlines(True):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            out.append(line)
            continue
        parts = line.split()
        if len(parts) >= 3 and parts[1] in wanted:
            mount, (fstype, uuid) = parts[1], wanted[parts[1]]
            ok_type = parts[2] == fstype or (mount == "/boot" and parts[2] in boot_types)
            if parts[0].startswith("UUID=") and ok_type:
                out.append(re.sub(r"^(\s*)UUID=\S+", rf"\g<1>UUID={uuid}", line, count=1))
                seen.add(mount)
                continue
            problems.append(f"{mount} ({parts[0]} {parts[2]})")
        if "swapfile" in line:
            out.append("# restored: swapfile left out (the new disk has none)\n# " + line)
        else:
            out.append(line)
    missing = sorted({"/", "/boot"} - seen)
    if missing or problems:
        raise BootFixError("fstab still names the old disk: "
                           + ", ".join([f"no UUID= line for {m}" for m in missing] + problems))
    return "".join(out)


# --- crypttab (checklist 3) --------------------------------------------------

def crypttab(text: str, luks_uuid: str, partuuid: str) -> str:
    """The root entry only (another disk named there isn't this rescue's).
    PARTUUID first: UUID= must not match the tail of PARTUUID=."""
    forms = [(rf"\bPARTUUID={HEX}", f"PARTUUID={partuuid}"),
             (rf"/dev/disk/by-partuuid/{HEX}", f"/dev/disk/by-partuuid/{partuuid}"),
             (rf"(?<![A-Za-z])UUID={HEX}", f"UUID={luks_uuid}"),
             (rf"/dev/disk/by-uuid/{HEX}", f"/dev/disk/by-uuid/{luks_uuid}")]
    out = []
    for line in text.splitlines(True):
        raw = line.strip()
        if not raw or raw.startswith("#") or raw.split()[0] != "root":
            out.append(line)
            continue
        for pattern, replacement in forms:
            new, n = re.subn(pattern, replacement, line, count=1)
            if n:
                out.append(new)
                break
        else:
            raise BootFixError("crypttab's root entry has no ID to point at the new disk")
    return "".join(out)


# --- the boot loader's settings (checklist 4, 7) -----------------------------

def cmdline(text: str, partuuid: str, luks_uuid: str = "") -> str:
    """cryptdevice and rd.luks to the new partition; hibernation resume
    removed (an old resume= would hang start-up on a new disk); Limine's hash
    pin on a UKI path dropped (the patched UKI no longer matches it)."""
    text = re.sub(rf"cryptdevice=PARTUUID={HEX}", f"cryptdevice=PARTUUID={partuuid}", text)
    if luks_uuid:
        text = re.sub(rf"rd\.luks\.uuid={HEX}", f"rd.luks.uuid={luks_uuid}", text)
        text = re.sub(rf"rd\.luks\.name={HEX}", f"rd.luks.name={luks_uuid}", text)
        text = re.sub(rf"rd\.luks\.options={HEX}", f"rd.luks.options={luks_uuid}", text)
    text = re.sub(r"[ \t]*resume_offset=[^\s\"]+", "", text)
    text = re.sub(r"[ \t]*resume=[^\s\"]*", "", text)
    text = re.sub(r"(path:\s*boot\(\):/EFI/Linux/[^\s#]+\.efi)#[0-9a-fA-F]+", r"\1", text)
    return text


def settings_files(root: Path, partuuid: str, luks_uuid: str, btrfs_uuid: str, esp_uuid: str) -> list[str]:
    """Checklist 2-4 on a restored root (@ mounted at `root`). Returns what changed."""
    done = []
    path = root / "etc/fstab"
    if not path.is_file():
        raise BootFixError("the restored system has no /etc/fstab")
    path.write_text(fstab(path.read_text(errors="replace"), btrfs_uuid, esp_uuid))
    done.append("etc/fstab")
    for rel in ("etc/crypttab", "etc/crypttab.initramfs"):
        if (root / rel).is_file():
            (root / rel).write_text(crypttab((root / rel).read_text(errors="replace"), luks_uuid, partuuid))
            done.append(rel)
    for rel in ["etc/default/limine", *(str(p.relative_to(root)) for p in
                                        sorted((root / "etc/limine-entry-tool.d").glob("*.conf")))]:
        p = root / rel
        if p.is_file():
            new = cmdline(p.read_text(errors="replace"), partuuid, luks_uuid)
            if "resume" in p.name and "resume" not in new:
                new = "# restored: hibernation resume left out (new disk)\n"
            p.write_text(new)
            done.append(rel)
    return done


# --- the boot partition: patch and VERIFY (checklist 7) ----------------------

def ukis(esp: Path) -> list[Path]:
    linux = esp / "EFI" / "Linux"
    return [p for p in sorted(linux.iterdir()) if p.suffix.lower() == ".efi" and ".bak" not in p.name.lower()] \
        if linux.is_dir() else []


def find_conf(esp: Path) -> Path | None:
    return next((p for p in (esp / "limine.conf", esp / "EFI" / "limine" / "limine.conf") if p.is_file()), None)


def _luks_ok(blob: str, luks_uuid: str) -> bool:
    return not luks_uuid or all(o.lower() == luks_uuid.lower()
                                for o in re.findall(rf"rd\.luks\.(?:uuid|name)=({HEX})", blob))


def verify(esp: Path, partuuid: str, luks_uuid: str = "") -> bool:
    """The boot entry and every UKI unlock THIS disk, and no other."""
    conf = find_conf(esp)
    if conf is None:
        return False
    text = conf.read_text(errors="replace")
    if set(re.findall(rf"cryptdevice=PARTUUID=({HEX})", text)) != {partuuid} or not _luks_ok(text, luks_uuid):
        return False
    found = False
    for uki in ukis(esp):
        raw = uki.read_bytes().decode("latin-1")
        others = re.findall(rf"cryptdevice=PARTUUID=({HEX})", raw)
        if f"cryptdevice=PARTUUID={partuuid}:" not in raw or any(o != partuuid for o in others) \
                or not _luks_ok(raw, luks_uuid):
            return False
        found = True
    return found


def drop_history(esp: Path) -> None:
    """The old machine's snapshot boot entries: every one names a partition
    that doesn't exist on this disk, so they could only fail."""
    for p in [*esp.glob("*/limine_history"), esp / "limine_history"]:
        shutil.rmtree(p, ignore_errors=True)


def _objcopy(args: list[str], chroot: Path) -> None:
    # The rescue system needn't carry binutils: objcopy from the restored one.
    subprocess.run(["arch-chroot", str(chroot), "objcopy", *args], check=True, capture_output=True)


def patch_uki(esp: Path, uki: Path, chroot: Path, partuuid: str, luks_uuid: str) -> None:
    tmp = esp / "uki-cmdline.bin"
    inside = "/boot/" + str(uki.relative_to(esp))
    try:
        _objcopy([f"--dump-section=.cmdline=/boot/{tmp.name}", inside], chroot)
        data = tmp.read_bytes()
        if not data:
            raise BootFixError(f"{uki.name} has an empty command line")
        old = data.split(b"\0", 1)[0].decode("utf-8", "replace")
        new = (cmdline(old, partuuid, luks_uuid).strip() + "\n").encode()
        if len(new) > len(data):
            raise BootFixError(f"{uki.name}'s new command line doesn't fit")
        tmp.write_bytes(new.ljust(len(data), b"\0"))
        _objcopy([f"--update-section=.cmdline=/boot/{tmp.name}", inside], chroot)
    finally:
        tmp.unlink(missing_ok=True)


def boot_entry(esp: Path, chroot: Path, partuuid: str, luks_uuid: str) -> None:
    """Patch what doesn't point at this disk yet, then verify; a disk that
    wouldn't unlock stops the rescue (1.x)."""
    drop_history(esp)
    if not verify(esp, partuuid, luks_uuid):
        conf = find_conf(esp)
        if conf is not None:
            conf.write_text(cmdline(conf.read_text(errors="replace"), partuuid, luks_uuid))
        for uki in ukis(esp):
            try:
                patch_uki(esp, uki, chroot, partuuid, luks_uuid)
            except (subprocess.CalledProcessError, OSError, BootFixError):
                pass          # the check below says whether it's good enough
    if not verify(esp, partuuid, luks_uuid):
        raise BootFixError("the restored disk's boot entry doesn't unlock it (it still names another disk)")
