"""The rescue's restore (stage 9b): 1.x's boot checklist on Omarchy 4.5's real
file shapes, the boot entry verified, Quick Rescue's folders left for later,
and each home told to offer Restore my files."""

import json
import subprocess
from pathlib import Path

import pytest

from omabackups.restore import bootfix, newdisk, system

OLD_BTRFS, OLD_ESP = "aaaaaaaa-0000-4000-8000-00000000000a", "AAAA-0001"
OLD_PART, OLD_LUKS = "bbbbbbbb-0000-4000-8000-00000000000b", "cccccccc-0000-4000-8000-00000000000c"
NEW = {"btrfs": "11111111-1111-4111-8111-111111111111", "esp": "ABCD-1234",
       "partuuid": "22222222-2222-4222-8222-222222222222", "luks": "33333333-3333-4333-8333-333333333333"}

FSTAB = f"""# Static information about the filesystems.
UUID={OLD_BTRFS}\t/         \tbtrfs     \trw,relatime,compress=zstd:3,subvol=/@\t0 0
UUID={OLD_BTRFS}\t/home     \tbtrfs     \trw,relatime,compress=zstd:3,subvol=/@home\t0 0
UUID={OLD_BTRFS}\t/var/cache/pacman/pkg\tbtrfs     \trw,relatime,subvol=/@pkg\t0 0
UUID={OLD_BTRFS}\t/var/log  \tbtrfs     \trw,relatime,subvol=/@log\t0 0
UUID={OLD_ESP}      \t/boot     \tvfat      \trw,relatime,fmask=0177,dmask=0077\t0 2
/swap/swapfile none swap defaults,pri=0 0 0
"""
LIMINE = (f'KERNEL_CMDLINE[default]+="cryptdevice=PARTUUID={OLD_PART}:root:allow-discards root=/dev/mapper/root '
          f'rootflags=subvol=@ rw rd.luks.name={OLD_LUKS}=root rd.luks.options={OLD_LUKS}=discard '
          f'resume=/dev/mapper/root resume_offset=533760 quiet"\n')


def test_fstab_points_at_the_new_disk_and_leaves_the_swapfile_out():
    text = bootfix.fstab(FSTAB, NEW["btrfs"], NEW["esp"])
    assert OLD_BTRFS not in text and OLD_ESP not in text
    assert text.count(f"UUID={NEW['btrfs']}") == 4 and f"UUID={NEW['esp']}" in text
    assert "\n# /swap/swapfile none swap" in text and "\n/swap/swapfile" not in text


def test_fstab_without_a_root_or_boot_line_stops_the_rescue():
    with pytest.raises(bootfix.BootFixError):
        bootfix.fstab(FSTAB.replace("\t/boot ", "\t/efi "), NEW["btrfs"], NEW["esp"])
    with pytest.raises(bootfix.BootFixError):
        bootfix.fstab(FSTAB.replace(f"UUID={OLD_BTRFS}\t/         ", "/dev/sda2\t/         "),
                      NEW["btrfs"], NEW["esp"])


def test_crypttab_changes_the_root_entry_only():
    text = f"root PARTUUID={OLD_PART} none luks\ndata UUID=44444444-0000-4000-8000-000000000000 none luks\n"
    out = bootfix.crypttab(text, NEW["luks"], NEW["partuuid"])
    assert f"root PARTUUID={NEW['partuuid']}" in out and "data UUID=44444444" in out
    assert bootfix.crypttab(f"root UUID={OLD_LUKS} none\n", NEW["luks"], NEW["partuuid"]) == \
        f"root UUID={NEW['luks']} none\n"


def test_the_boot_loader_settings_name_the_new_disk_and_lose_resume():
    out = bootfix.cmdline(LIMINE, NEW["partuuid"], NEW["luks"])
    assert f"cryptdevice=PARTUUID={NEW['partuuid']}:root" in out
    assert f"rd.luks.name={NEW['luks']}=root" in out and f"rd.luks.options={NEW['luks']}=discard" in out
    assert OLD_PART not in out and OLD_LUKS not in out
    assert "resume" not in out and out.rstrip().endswith('quiet"')
    pinned = "path: boot():/EFI/Linux/omarchy_linux-omarchy.efi#abc123def\n"
    assert bootfix.cmdline(pinned, "x") == "path: boot():/EFI/Linux/omarchy_linux-omarchy.efi\n"


def test_the_restored_systems_files_all_get_fixed(tmp_path):
    root = tmp_path / "@"
    for rel, text in {"etc/fstab": FSTAB, "etc/default/limine": LIMINE,
                      "etc/limine-entry-tool.d/resume.conf": f"KERNEL_CMDLINE[default]+=\"resume_offset=1\"\n",
                      "etc/crypttab.initramfs": f"root PARTUUID={OLD_PART} none\n"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    done = bootfix.settings_files(root, NEW["partuuid"], NEW["luks"], NEW["btrfs"], NEW["esp"])
    assert set(done) == {"etc/fstab", "etc/default/limine", "etc/limine-entry-tool.d/resume.conf",
                         "etc/crypttab.initramfs"}
    for rel in done:
        text = (root / rel).read_text()
        assert OLD_PART not in text and OLD_LUKS not in text and OLD_BTRFS not in text
    assert "resume" not in (root / "etc/default/limine").read_text()
    with pytest.raises(bootfix.BootFixError):
        bootfix.settings_files(tmp_path / "empty", "a", "b", "c", "d")


def esp_with(tmp_path, cmd: str) -> Path:
    esp = tmp_path / "esp"
    (esp / "EFI/Linux").mkdir(parents=True)
    (esp / "limine.conf").write_text(f"/Omarchy\n  cmdline: {cmd}\n")
    (esp / "EFI/Linux/omarchy_linux-omarchy.efi").write_bytes(b"MZ\0\0.cmdline\0" + cmd.encode() + b"\0\0")
    (esp / "limine_history").mkdir()
    return esp


def test_the_boot_entry_is_verified_against_this_disk(tmp_path):
    good = f"cryptdevice=PARTUUID={NEW['partuuid']}:root rd.luks.name={NEW['luks']}=root"
    esp = esp_with(tmp_path, good)
    assert bootfix.verify(esp, NEW["partuuid"], NEW["luks"])
    assert not bootfix.verify(esp, OLD_PART, NEW["luks"])
    bootfix.boot_entry(esp, tmp_path, NEW["partuuid"], NEW["luks"])        # already right: only history goes
    assert not (esp / "limine_history").exists()


def test_a_boot_entry_that_still_names_the_old_disk_stops_the_rescue(tmp_path):
    esp = esp_with(tmp_path, f"cryptdevice=PARTUUID={OLD_PART}:root rd.luks.name={OLD_LUKS}=root")
    with pytest.raises(bootfix.BootFixError):
        bootfix.boot_entry(esp, tmp_path / "no-chroot", NEW["partuuid"], NEW["luks"])
    assert NEW["partuuid"] in (esp / "limine.conf").read_text()            # the entry was fixed...
    assert not bootfix.verify(esp, NEW["partuuid"], NEW["luks"])           # ...the UKI couldn't be: stopped


def test_quick_rescue_leaves_the_folders_and_what_can_be_fetched_again(tmp_path):
    src, dest = tmp_path / "home", tmp_path / "restored"
    steam = "u/.local/share/Steam"
    for rel in ("u/.config/app/conf", "u/.local/bin/claude", "u/.cache/big", "u/.ollama/models/m",
                "u/.ollama/id_ed25519", f"{steam}/config/loginusers.vdf", f"{steam}/steamapps/compatdata/1/save",
                f"{steam}/steamapps/common/Game/game.bin", f"{steam}/steamapps/appmanifest_1.acf",
                "u/.local/share/bottles/bottles/b/drive_c/save", "u/.local/share/bottles/runners/wine/bin",
                "u/Documents/letter.txt", "u/Projects/x/main.py", "u/.bashrc"):
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_text("x")
    subprocess.run(["rsync", "-a", *system.home_filter(False), f"{src}/", f"{dest}/"], check=True)
    have = {str(p.relative_to(dest)) for p in dest.rglob("*")}
    # A program's settings, logins and saves come back now: Steam opens logged in.
    assert {"u/.config/app/conf", "u/.local/bin/claude", "u/.bashrc", "u/Documents", "u/Projects",
            "u/.ollama/id_ed25519", f"{steam}/config/loginusers.vdf", f"{steam}/steamapps/compatdata/1/save",
            "u/.local/share/bottles/bottles/b/drive_c/save"} <= have
    # The big part you can get again waits for Restore my files.
    assert not {"u/.cache/big", "u/.ollama/models/m", f"{steam}/steamapps/common",
                f"{steam}/steamapps/appmanifest_1.acf", "u/.local/share/bottles/runners",
                "u/Documents/letter.txt", "u/Projects/x"} & have
    assert system.home_filter(True) == []


def test_each_home_is_told_to_offer_restore_my_files(tmp_path):
    root = tmp_path / "root"
    (root / "home/u/Documents").mkdir(parents=True)
    (root / "home/u/Music").mkdir()
    system._record(root, "004-2026-11-10-1753", full=False)
    mine = json.loads((root / "home/u/.local/state/omabackups/migrate.json").read_text())
    assert mine["files"] == ["Documents", "Music"] and mine["files_restored"] is False
    assert mine["later"] == ["models", "games", "flatpak", "vms"]      # the Quick skips, later
    assert mine["from_user"] == "u" and mine["point"] == "004-2026-11-10-1753"
    assert json.loads((root / "var/lib/omabackups/rescued.json").read_text())["point"] == "004-2026-11-10-1753"


def test_partitions_are_named_as_the_kernel_names_them():
    assert newdisk.partition("/dev/sda", 1) == "/dev/sda1"
    assert newdisk.partition("/dev/nvme0n1", 2) == "/dev/nvme0n1p2"
    assert newdisk.partition("/dev/vda", 2) == "/dev/vda2"


class _Disk:
    """A disk whose new layout shows up after a few looks (old IDs until then)."""
    def __init__(self, shows_after: int, rereadpt_ok: bool = True):
        self.looks, self.shows_after, self.rereadpt_ok, self.calls = 0, shows_after, rereadpt_ok, []

    def run(self, cmd, **kw):
        self.calls.append(cmd[0])
        out, code = "", 0
        if cmd[:2] == ["sgdisk", "-i"]:
            out = f"Partition GUID code: X\nPartition unique GUID: {'AAAA-1' if cmd[2] == '1' else 'AAAA-2'}\n"
        elif cmd[0] == "lsblk":
            self.looks += 1
            new = self.looks > 2 * self.shows_after
            out = ("aaaa-1" if cmd[-1].endswith("1") else "aaaa-2") if new else "old-id"
        elif cmd[0] == "blockdev":
            code = 0 if self.rereadpt_ok else 1
        text = kw.get("text")
        return subprocess.CompletedProcess(cmd, code, out if text else out.encode(), "" if text else b"")


def _fake_disk(monkeypatch, disk):
    monkeypatch.setattr(newdisk.subprocess, "run", disk.run)
    monkeypatch.setattr(newdisk.os.path, "exists", lambda p: True)
    monkeypatch.setattr(newdisk.time, "sleep", lambda s: None)


def test_nothing_is_written_until_the_new_layout_shows(monkeypatch):
    disk = _Disk(shows_after=3)
    _fake_disk(monkeypatch, disk)
    newdisk.settle(newdisk.NewDisk("/dev/sdz", "/dev/sdz1", "/dev/sdz2"))
    assert disk.looks >= 6 and "partprobe" not in disk.calls and "udevadm" in disk.calls


def test_a_busy_disk_is_reread_with_partx(monkeypatch):
    disk = _Disk(shows_after=1, rereadpt_ok=False)
    _fake_disk(monkeypatch, disk)
    newdisk.settle(newdisk.NewDisk("/dev/sdz", "/dev/sdz1", "/dev/sdz2"))
    assert "partx" in disk.calls


def test_a_layout_that_never_shows_stops_before_anything_is_written(monkeypatch):
    disk = _Disk(shows_after=10_000)
    _fake_disk(monkeypatch, disk)
    with pytest.raises(newdisk.OmaError) as caught:
        newdisk.settle(newdisk.NewDisk("/dev/sdz", "/dev/sdz1", "/dev/sdz2"))
    assert "Nothing was taken" in caught.value.todo and "old-id" in caught.value.details


def test_a_network_drop_mid_rescue_stops_it_with_what_to_do(tmp_path):
    """Stage 10: the connection goes while the rescue copies: it stops with
    what happened and what to do (run it again), never a half-said error."""
    from omabackups.core.errors import OmaError

    class DroppedLine:
        def rsh(self):
            return "false"                     # ssh that fails at once

        def rsync_target(self):
            return "omabackups-gate@192.0.2.34"

        def rsync_env(self):
            return None
    with pytest.raises(OmaError) as caught:
        system.fetch(DroppedLine(), "b" * 32, "004-2026-11-10-2103", "system", tmp_path / "@", [],
                     lambda f: None)
    assert caught.value.code == "rescue-copy"
    assert "again" in caught.value.todo and caught.value.details
